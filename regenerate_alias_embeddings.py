"""
Regenerate Embeddings for Alias Products
=========================================

Problem: Alias products have special characters like ' that should be removed
Solution: Update embedding_text and regenerate embeddings

Steps:
1. Find all alias products
2. Clean embedding_text (remove non-letter/space chars)
3. Regenerate embeddings using batch API
"""

import os
import re
import time
from openai import OpenAI
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}

client = OpenAI(api_key=OPENAI_API_KEY)
BATCH_SIZE = 500


def clean_embedding_text(text):
    """
    Clean embedding text to match StockX format
    - Remove single quotes ('), hyphens, underscores
    - Keep numbers, letters, spaces, parentheses, forward slashes
    - Expand Wmns → (Women's)

    Examples:
    - "DD0385 100 Air Max 90 'Cork'" → "DD0385100 Air Max 90 Cork"
    - "BB6168 UltraBoost 4.0 'Triple White'" → "BB6168 UltraBoost 4.0 Triple White"
    - "Wmns Air Jordan 11" → "(Women's) Air Jordan 11"
    """
    if not text:
        return text

    # Split into SKU and name parts
    parts = text.split(' ', 1)

    if len(parts) == 2:
        sku_part = parts[0]
        name_part = parts[1]

        # Expand Wmns in name
        name_part = re.sub(r'\bWmns\b', "(Women's)", name_part, flags=re.IGNORECASE)

        # Remove single quotes, hyphens, underscores from name
        name_part = name_part.replace("'", '').replace('-', ' ').replace('_', ' ')

        # Normalize spaces in name
        name_part = re.sub(r'\s+', ' ', name_part).strip()

        return f"{sku_part} {name_part}"
    else:
        # Just name, no SKU
        text = re.sub(r'\bWmns\b', "(Women's)", text, flags=re.IGNORECASE)
        text = text.replace("'", '').replace('-', ' ').replace('_', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text


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


def main():
    print("\n" + "="*80)
    print("REGENERATE ALIAS EMBEDDINGS - Remove Special Characters")
    print("="*80)

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Fetch all alias products
    print("\n📊 Fetching alias products...")
    cur.execute("""
        SELECT
            product_id_internal,
            embedding_text,
            product_name_platform
        FROM products
        WHERE platform = 'alias'
        ORDER BY product_id_internal
    """)

    products = cur.fetchall()
    total = len(products)

    print(f"   ✅ Found {total:,} alias products")

    # Show examples of what will change
    print("\n📝 Example transformations:")
    for i in range(min(5, total)):
        old_text = products[i][1]
        new_text = clean_embedding_text(old_text)
        if old_text != new_text:
            print(f"   OLD: {old_text}")
            print(f"   NEW: {new_text}")
            print()

    print(f"\n💰 Estimated cost: ${total * 0.02 / 1000000:.2f}")
    print(f"⏱️  Estimated time: 2-5 minutes")

    response = input("\nContinue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    print(f"\n🚀 Processing {total:,} products in batches of {BATCH_SIZE}...\n")
    start_time = time.time()

    stats = {'updated_text': 0, 'updated_embedding': 0, 'failed': 0}

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = products[batch_start:batch_end]

        # Prepare batch
        product_ids = [p[0] for p in batch]
        old_texts = [p[1] for p in batch]
        new_texts = [clean_embedding_text(t) if t else "" for t in old_texts]

        # Generate embeddings for cleaned texts
        embeddings = generate_embeddings_batch(new_texts)

        if not embeddings or len(embeddings) != len(batch):
            print(f"   ❌ Batch {batch_start:,}-{batch_end:,} failed")
            stats['failed'] += len(batch)
            continue

        # Update database (embedding_text + embedding)
        for product_id, new_text, embedding in zip(product_ids, new_texts, embeddings):
            try:
                cur.execute("""
                    UPDATE products
                    SET embedding_text = %s,
                        embedding = %s::vector
                    WHERE product_id_internal = %s
                """, (new_text, embedding, product_id))
                stats['updated_text'] += 1
                stats['updated_embedding'] += 1
            except Exception as e:
                print(f"   ❌ Update failed for product {product_id}: {e}")
                stats['failed'] += 1

        conn.commit()

        # Progress
        elapsed = time.time() - start_time
        rate = batch_end / elapsed if elapsed > 0 else 0
        eta = (total - batch_end) / rate if rate > 0 else 0

        print(f"   Progress: {batch_end:,}/{total:,} ({batch_end/total*100:.1f}%)")
        print(f"   Rate: {rate:.0f} products/sec | ETA: {eta:.0f}s\n")

    # Final stats
    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"✅ Updated embedding_text:  {stats['updated_text']:,}")
    print(f"✅ Updated embeddings:      {stats['updated_embedding']:,}")
    print(f"❌ Failed:                  {stats['failed']:,}")
    print(f"\n⏱️  Total time: {elapsed/60:.2f} minutes ({elapsed:.0f} seconds)")
    print(f"⚡ Rate: {total/elapsed:.0f} products/sec")
    print(f"💰 Actual cost: ${total * 0.02 / 1000000:.2f}")

    cur.close()
    conn.close()

    print("\n✅ Alias embedding regeneration complete!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
