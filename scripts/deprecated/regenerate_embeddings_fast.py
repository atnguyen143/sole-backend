"""
Regenerate Embeddings - FAST BATCH VERSION
===========================================

Uses OpenAI batch API (up to 2048 items per request)

Speed: ~500-1000 products/sec
Time: 2-5 minutes for 124K products (vs 2 hours!)
Cost: ~$2.00 (same)
"""

import os
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

BATCH_SIZE = 500  # OpenAI allows up to 2048


def generate_embeddings_batch(texts, retry_count=3):
    """Generate embeddings for multiple texts in ONE API call"""
    for attempt in range(retry_count):
        try:
            response = client.embeddings.create(
                input=texts,  # List of texts
                model="text-embedding-3-small"
            )
            # Returns embeddings in same order as input
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
    print("REGENERATE EMBEDDINGS - FAST BATCH VERSION")
    print("="*80)

    # Fetch all products
    print("\n📊 Fetching products...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            product_id_internal,
            embedding_text
        FROM products
        ORDER BY product_id_internal
    """)

    products = cur.fetchall()
    total = len(products)

    print(f"   ✅ Found {total:,} products")
    print(f"\n⚡ Using batch size: {BATCH_SIZE} products per API call")
    print(f"📊 Total batches: {(total + BATCH_SIZE - 1) // BATCH_SIZE}")
    print(f"💰 Estimated cost: ${total * 0.02 / 1000000:.2f}")
    print(f"⏱️  Estimated time: 2-5 minutes\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    print(f"\n🚀 Processing {total:,} products in batches of {BATCH_SIZE}...\n")
    start_time = time.time()

    stats = {'generated': 0, 'updated': 0, 'failed': 0}

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = products[batch_start:batch_end]

        # Prepare batch
        product_ids = [p[0] for p in batch]
        texts = [p[1] if p[1] else "" for p in batch]  # Use embedding_text as-is (don't uppercase)

        # Generate embeddings for entire batch in ONE API call
        embeddings = generate_embeddings_batch(texts)

        if not embeddings or len(embeddings) != len(batch):
            print(f"   ❌ Batch {batch_start:,}-{batch_end:,} failed")
            stats['failed'] += len(batch)
            continue

        # Update database
        for product_id, embedding in zip(product_ids, embeddings):
            try:
                cur.execute("""
                    UPDATE products
                    SET embedding = %s::vector
                    WHERE product_id_internal = %s
                """, (embedding, product_id))
                stats['updated'] += 1
            except Exception as e:
                print(f"   ❌ Update failed for product {product_id}: {e}")
                stats['failed'] += 1

        conn.commit()
        stats['generated'] += len(embeddings)

        # Progress
        elapsed = time.time() - start_time
        rate = (batch_end) / elapsed if elapsed > 0 else 0
        eta = (total - batch_end) / rate if rate > 0 else 0

        print(f"   Progress: {batch_end:,}/{total:,} ({batch_end/total*100:.1f}%)")
        print(f"   Rate: {rate:.0f} products/sec | ETA: {eta:.0f}s\n")

    # Final stats
    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"✅ Generated:  {stats['generated']:,}")
    print(f"✅ Updated:    {stats['updated']:,}")
    print(f"❌ Failed:     {stats['failed']:,}")
    print(f"\n⏱️  Total time: {elapsed/60:.2f} minutes ({elapsed:.0f} seconds)")
    print(f"⚡ Rate: {total/elapsed:.0f} products/sec")
    print(f"💰 Actual cost: ${total * 0.02 / 1000000:.2f}")

    cur.close()
    conn.close()

    print("\n✅ Embedding regeneration complete!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
