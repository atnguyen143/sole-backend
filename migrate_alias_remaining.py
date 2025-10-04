"""
Migrate Remaining Alias Products
=================================

Migrates ~282K remaining alias products from MySQL to Supabase
With cleaned embedding text (no special characters)

Estimated cost: ~$11.30
Estimated time: 10-15 minutes (with batch API)
"""

import os
import re
import time
import pymysql
import psycopg2
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
}
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}

client = OpenAI(api_key=OPENAI_API_KEY)
BATCH_SIZE = 500


def normalize_text_for_embedding(text):
    """
    Normalize text for embeddings (StockX style)
    - Remove: hyphens, underscores, single quotes (')
    - Keep: forward slashes, parentheses, apostrophes in contractions
    - Expand abbreviations (Wmns → (Women's))
    - Keep original case

    Examples:
    - "Air Max 90 'Cork'" → "Air Max 90 Cork" (quotes removed)
    - "Dunk Low 'Light-Carbon'" → "Dunk Low Light Carbon"
    - "Wmns Air Jordan 11 Retro" → "(Women's) Air Jordan 11 Retro"
    - "Nike Air Force 1 '07" → "Nike Air Force 1 07" (year quote removed)
    """
    if not text:
        return ""

    # Expand abbreviations (case-insensitive replacements)
    # Wmns → (Women's) - match StockX pattern
    text = re.sub(r'\bWmns\b', "(Women's)", text, flags=re.IGNORECASE)

    # Remove single quotes ('), hyphens, underscores
    text = text.replace("'", '').replace('-', ' ').replace('_', ' ')

    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_embedding_text_alias(name, sku=None):
    """
    Generate embedding text for alias products (MATCH STOCKX FORMAT)
    Format: "NORMALIZEDSKU product name" (NO SPACE in SKU, keep apostrophes/special chars in name)

    Examples:
    - sku="DD0385 100", name="Air Max 90 'Cork'" → "DD0385100 Air Max 90 'Cork'"
    - sku="BB6168", name="UltraBoost 4.0 'Triple White'" → "BB6168 UltraBoost 4.0 'Triple White'"
    - sku="FJ4188 100", name="Dunk Low SE 'Light-Carbon'" → "FJ4188100 Dunk Low SE 'Light Carbon'"
    """
    # Normalize name (remove - and _ but KEEP apostrophes, parentheses, etc.)
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if sku:
        # Normalize SKU: remove ALL spaces, dashes, underscores (SKU part only)
        normalized_sku = sku.replace('-', '').replace('_', '').replace(' ', '')
        return f"{normalized_sku} {normalized_name}".strip()

    return normalized_name


def normalize_style_id(style_id):
    """
    Normalize style ID for storage
    - Remove -, _, spaces
    - Uppercase
    - Strip leading zeros (unless it's just "0")
    """
    if not style_id or str(style_id).strip() == '':
        return None

    normalized = str(style_id).replace('-', '').replace(' ', '').replace('_', '')
    normalized = normalized.upper()

    if normalized != '0':
        normalized = normalized.lstrip('0') or '0'

    return normalized if normalized else None


def generate_embeddings_batch(texts, retry_count=3):
    """Generate embeddings for multiple texts in ONE API call"""
    for attempt in range(retry_count):
        try:
            response = client.embeddings.create(
                input=texts,
                model="text-embedding-3-small"
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            if attempt < retry_count - 1:
                print(f"   ⚠️  Retry {attempt + 1}/{retry_count}: {e}")
                time.sleep(2 ** attempt)
            else:
                print(f"   ❌ Batch failed: {e}")
                return None
    return None


def fetch_remaining_alias_products():
    """Fetch alias products not yet migrated"""
    print("\n📦 Fetching remaining alias products from MySQL...")

    # Get migrated IDs from Supabase
    supa_conn = psycopg2.connect(**SUPABASE_CONFIG)
    supa_cur = supa_conn.cursor()
    supa_cur.execute("SELECT product_id_platform FROM products WHERE platform = 'alias'")
    migrated_ids = {row[0] for row in supa_cur.fetchall()}
    supa_cur.close()
    supa_conn.close()

    print(f"   Found {len(migrated_ids):,} already migrated")

    # Fetch all from MySQL
    mysql_conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute("""
        SELECT catalogId, name, sku, keywordUsed
        FROM alias_products
    """)
    all_products = mysql_cur.fetchall()
    mysql_cur.close()
    mysql_conn.close()

    # Filter out migrated
    remaining = [p for p in all_products if p['catalogId'] not in migrated_ids]

    print(f"   ✅ Found {len(remaining):,} remaining products to migrate\n")
    return remaining


def main():
    print("\n" + "="*80)
    print("MIGRATE REMAINING ALIAS PRODUCTS")
    print("="*80)

    # Fetch remaining products
    products = fetch_remaining_alias_products()
    total = len(products)

    if total == 0:
        print("✅ No remaining products to migrate!")
        return

    print(f"📊 Total to migrate: {total:,}")
    print(f"💰 Estimated cost: ${total * 0.02 / 1000000:.2f}")
    print(f"⏱️  Estimated time: 10-15 minutes")

    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    print(f"\n🚀 Processing {total:,} products in batches of {BATCH_SIZE}...\n")
    start_time = time.time()

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    stats = {'inserted': 0, 'failed': 0, 'inventory_updated': 0}

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = products[batch_start:batch_end]

        # Prepare embedding texts
        texts = []
        for p in batch:
            embedding_text = generate_embedding_text_alias(p['name'], p['sku'])
            texts.append(embedding_text)

        # Generate embeddings
        embeddings = generate_embeddings_batch(texts)

        if not embeddings or len(embeddings) != len(batch):
            print(f"   ❌ Batch {batch_start:,}-{batch_end:,} failed")
            stats['failed'] += len(batch)
            continue

        # Insert into products and get product_id_internal
        product_id_map = {}  # catalogId -> product_id_internal

        for product, embedding_text, embedding in zip(batch, texts, embeddings):
            try:
                cur.execute("""
                    INSERT INTO products (
                        product_id_platform,
                        platform,
                        product_name_platform,
                        style_id_platform,
                        style_id_normalized,
                        embedding_text,
                        embedding,
                        keyword_used
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (product_id_platform, platform) DO NOTHING
                    RETURNING product_id_internal
                """, (
                    product['catalogId'],
                    'alias',
                    (product['name'] or '').upper(),  # Store uppercase
                    product['sku'],
                    normalize_style_id(product['sku']),
                    embedding_text,  # Cleaned text
                    embedding,
                    product.get('keywordUsed')  # Include keyword
                ))

                result = cur.fetchone()
                if result:
                    product_id_internal = result[0]
                    product_id_map[product['catalogId']] = product_id_internal
                    stats['inserted'] += 1

            except Exception as e:
                print(f"   ❌ Insert failed for {product['catalogId']}: {e}")
                stats['failed'] += 1

        # Update inventory table with new product_id_internal links
        for catalog_id, product_id_internal in product_id_map.items():
            try:
                cur.execute("""
                    UPDATE inventory
                    SET product_id_internal = %s
                    WHERE alias_catalog_id = %s
                      AND product_id_internal IS NULL
                """, (product_id_internal, catalog_id))

                if cur.rowcount > 0:
                    stats['inventory_updated'] += cur.rowcount

            except Exception as e:
                print(f"   ⚠️  Inventory update failed for {catalog_id}: {e}")

        conn.commit()

        # Progress
        elapsed = time.time() - start_time
        rate = batch_end / elapsed if elapsed > 0 else 0
        eta = (total - batch_end) / rate if rate > 0 else 0

        print(f"   Progress: {batch_end:,}/{total:,} ({batch_end/total*100:.1f}%)")
        print(f"   Rate: {rate:.0f} products/sec | ETA: {eta/60:.1f}min\n")

    # Final stats
    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"✅ Inserted:           {stats['inserted']:,}")
    print(f"🔗 Inventory Updated:  {stats['inventory_updated']:,}")
    print(f"❌ Failed:             {stats['failed']:,}")
    print(f"\n⏱️  Total time: {elapsed/60:.2f} minutes")
    print(f"⚡ Rate: {total/elapsed:.0f} products/sec")
    print(f"💰 Actual cost: ${total * 0.02 / 1000000:.2f}")

    cur.close()
    conn.close()

    print("\n✅ Alias migration complete!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
