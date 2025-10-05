"""
MASTER MIGRATION - FRESH START
===============================

Complete fresh migration in steps:
1. Insert all StockX products (NO embeddings yet)
2. Insert all Alias products (NO embeddings yet)
3. Generate embeddings for ALL products in batches
4. Create vector index
5. Create product mappings

This ensures consistent embeddings with correct case/format.

Estimated cost: ~$18 (461K products × $0.02/1M tokens)
Estimated time: 30-60 minutes
"""

import os
import re
import time
import pymysql
import psycopg2
import psycopg2.extras
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
    """
    if not text:
        return ""

    # Expand abbreviations
    text = re.sub(r'\bWmns\b', "(Women's)", text, flags=re.IGNORECASE)

    # Remove single quotes ('), hyphens, underscores
    text = text.replace("'", '').replace('-', ' ').replace('_', ' ')

    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_embedding_text_stockx(name, style_id=None):
    """
    Generate embedding text for StockX products
    Format: "product name STYLEID" (space before style ID, original case)

    Examples:
    - name="Air Max 90 'Cork'", style_id="DD0385-100" → "Air Max 90 Cork DD0385100"
    """
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if style_id:
        normalized_style = style_id.replace('-', '').replace('_', '').replace(' ', '').upper()
        return f"{normalized_name} {normalized_style}".strip()

    return normalized_name


def generate_embedding_text_alias(name, sku=None):
    """
    Generate embedding text for alias products
    Format: "NORMALIZEDSKU product name" (NO SPACE in SKU, original case)

    Examples:
    - sku="DD0385 100", name="Air Max 90 'Cork'" → "DD0385100 Air Max 90 Cork"
    """
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if sku:
        normalized_sku = sku.replace('-', '').replace('_', '').replace(' ', '').upper()
        return f"{normalized_sku} {normalized_name}".strip()

    return normalized_name


def normalize_style_id(style_id):
    """Normalize style ID for storage"""
    if not style_id or str(style_id).strip() == '':
        return None

    normalized = str(style_id).replace('-', '').replace(' ', '').replace('_', '').upper()

    if normalized != '0':
        normalized = normalized.lstrip('0') or '0'

    return normalized if normalized else None


# ============================================================================
# STEP 1: Insert StockX Products (NO embeddings)
# ============================================================================

def step1_insert_stockx():
    """Insert all StockX products without embeddings"""
    print("\n" + "="*80)
    print("STEP 1: INSERT STOCKX PRODUCTS (NO EMBEDDINGS)")
    print("="*80 + "\n")

    # Fetch from MySQL
    print("📦 Fetching StockX products from MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute("SELECT productId, title, styleId FROM stockx_products")
    products = mysql_cur.fetchall()
    mysql_cur.close()
    mysql_conn.close()

    total = len(products)
    print(f"   ✅ Found {total:,} StockX products\n")

    # Insert to Supabase
    print("💾 Inserting to Supabase...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for batch_start in range(0, total, BATCH_SIZE):
        batch = products[batch_start:batch_start + BATCH_SIZE]

        values_list = []
        for p in batch:
            embedding_text = generate_embedding_text_stockx(p['title'], p['styleId'])
            values_list.append((
                p['productId'],
                'stockx',
                (p['title'] or '').upper(),
                p['styleId'],
                normalize_style_id(p['styleId']),
                embedding_text,
                None  # NO embedding yet
            ))

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO products (
                product_id_platform,
                platform,
                product_name_platform,
                style_id_platform,
                style_id_normalized,
                embedding_text,
                embedding
            ) VALUES %s
            ON CONFLICT (product_id_platform, platform)
            DO UPDATE SET
                embedding_text = EXCLUDED.embedding_text,
                embedding = NULL
            """,
            values_list,
            template="(%s, %s, %s, %s, %s, %s, %s::vector)"
        )

        inserted += len(batch)
        conn.commit()
        print(f"   Progress: {inserted:,}/{total:,} ({inserted/total*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n✅ Inserted {inserted:,} StockX products\n")
    return inserted


# ============================================================================
# STEP 2: Insert Alias Products (NO embeddings)
# ============================================================================

def step2_insert_alias():
    """Insert all Alias products without embeddings"""
    print("\n" + "="*80)
    print("STEP 2: INSERT ALIAS PRODUCTS (NO EMBEDDINGS)")
    print("="*80 + "\n")

    # Fetch from MySQL
    print("📦 Fetching Alias products from MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute("SELECT catalogId, name, sku, keywordUsed FROM alias_products")
    products = mysql_cur.fetchall()
    mysql_cur.close()
    mysql_conn.close()

    total = len(products)
    print(f"   ✅ Found {total:,} Alias products\n")

    # Insert to Supabase
    print("💾 Inserting to Supabase...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for batch_start in range(0, total, BATCH_SIZE):
        batch = products[batch_start:batch_start + BATCH_SIZE]

        values_list = []
        for p in batch:
            embedding_text = generate_embedding_text_alias(p['name'], p['sku'])
            values_list.append((
                p['catalogId'],
                'alias',
                (p['name'] or '').upper(),
                p['sku'],
                normalize_style_id(p['sku']),
                embedding_text,
                None,  # NO embedding yet
                p.get('keywordUsed')
            ))

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO products (
                product_id_platform,
                platform,
                product_name_platform,
                style_id_platform,
                style_id_normalized,
                embedding_text,
                embedding,
                keyword_used
            ) VALUES %s
            ON CONFLICT (product_id_platform, platform)
            DO UPDATE SET
                embedding_text = EXCLUDED.embedding_text,
                embedding = NULL
            """,
            values_list,
            template="(%s, %s, %s, %s, %s, %s, %s::vector, %s)"
        )

        inserted += len(batch)
        conn.commit()
        print(f"   Progress: {inserted:,}/{total:,} ({inserted/total*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n✅ Inserted {inserted:,} Alias products\n")
    return inserted


# ============================================================================
# STEP 3: Generate ALL Embeddings
# ============================================================================

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


def step3_generate_embeddings():
    """Generate embeddings for ALL products"""
    print("\n" + "="*80)
    print("STEP 3: GENERATE EMBEDDINGS FOR ALL PRODUCTS")
    print("="*80 + "\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Count products needing embeddings
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NULL AND embedding_text IS NOT NULL")
    total = cur.fetchone()[0]

    print(f"📊 Found {total:,} products needing embeddings")
    print(f"💰 Estimated cost: ${total * 0.02 / 1000000:.2f}")
    print(f"⏱️  Estimated time: {total / 500 * 2 / 60:.1f} minutes\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        cur.close()
        conn.close()
        return 0

    print("\n🚀 Processing...\n")
    start_time = time.time()

    processed = 0
    for offset in range(0, total, BATCH_SIZE):
        # Fetch batch
        cur.execute("""
            SELECT product_id_internal, embedding_text
            FROM products
            WHERE embedding IS NULL AND embedding_text IS NOT NULL
            ORDER BY product_id_internal
            LIMIT %s OFFSET %s
        """, (BATCH_SIZE, offset))

        batch = cur.fetchall()
        if not batch:
            break

        # Generate embeddings
        texts = [row[1] for row in batch]
        embeddings = generate_embeddings_batch(texts)

        if not embeddings or len(embeddings) != len(batch):
            print(f"   ❌ Batch {offset:,}-{offset+len(batch):,} failed")
            continue

        # Update database
        for (product_id, _), embedding in zip(batch, embeddings):
            cur.execute("""
                UPDATE products
                SET embedding = %s::vector
                WHERE product_id_internal = %s
            """, (embedding, product_id))

        conn.commit()
        processed += len(batch)

        # Progress
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0

        print(f"   Progress: {processed:,}/{total:,} ({processed/total*100:.1f}%) | Rate: {rate:.0f}/sec | ETA: {eta/60:.1f}min")

    cur.close()
    conn.close()

    elapsed = time.time() - start_time
    print(f"\n✅ Generated {processed:,} embeddings in {elapsed/60:.2f} minutes")
    print(f"💰 Actual cost: ${processed * 0.02 / 1000000:.2f}\n")

    return processed


# ============================================================================
# STEP 4: Create Vector Index
# ============================================================================

def step4_create_index():
    """Create vector index on embeddings"""
    print("\n" + "="*80)
    print("STEP 4: CREATE VECTOR INDEX")
    print("="*80 + "\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Count products with embeddings
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    total = cur.fetchone()[0]

    optimal_lists = int(total ** 0.5)

    print(f"📊 Found {total:,} products with embeddings")
    print(f"🎯 Optimal lists: {optimal_lists}")
    print(f"\n⏱️  This will take 2-10 minutes with upgraded compute\n")

    response = input("Create index? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        cur.close()
        conn.close()
        return False

    print("\n🚀 Creating index...\n")
    print("   💡 Run this SQL in Supabase SQL Editor for better control:\n")
    print(f"   SET maintenance_work_mem = '512MB';")
    print(f"   CREATE INDEX idx_products_embedding ON products")
    print(f"   USING ivfflat (embedding vector_cosine_ops)")
    print(f"   WITH (lists = {optimal_lists});\n")

    print("   Or let this script try (may timeout)...\n")

    try:
        cur.execute("SET maintenance_work_mem = '512MB'")
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_products_embedding
            ON products
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {optimal_lists})
        """)
        conn.commit()
        print("✅ Index created!\n")
        success = True
    except Exception as e:
        print(f"❌ Failed: {e}")
        print("\n   Please create index manually in Supabase SQL Editor\n")
        success = False

    cur.close()
    conn.close()

    return success


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("\n" + "="*80)
    print("MASTER MIGRATION - FRESH START")
    print("="*80)
    print("\nThis will:")
    print("1. Insert all StockX products (no embeddings)")
    print("2. Insert all Alias products (no embeddings)")
    print("3. Generate embeddings for ALL products")
    print("4. Create vector index")
    print("\nEstimated cost: ~$18")
    print("Estimated time: 30-60 minutes")
    print("\n" + "="*80 + "\n")

    response = input("Start fresh migration? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    # Execute steps
    stockx_count = step1_insert_stockx()
    alias_count = step2_insert_alias()
    embedding_count = step3_generate_embeddings()
    index_created = step4_create_index()

    # Summary
    print("\n" + "="*80)
    print("MIGRATION COMPLETE")
    print("="*80)
    print(f"✅ StockX products:    {stockx_count:,}")
    print(f"✅ Alias products:     {alias_count:,}")
    print(f"✅ Embeddings created: {embedding_count:,}")
    print(f"{'✅' if index_created else '⚠️ '} Vector index:       {'Created' if index_created else 'Manual creation needed'}")
    print("\n🎉 Ready for product mapping!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
