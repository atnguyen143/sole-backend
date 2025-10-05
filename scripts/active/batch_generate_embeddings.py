"""
BATCH EMBEDDINGS GENERATION
============================

Uses OpenAI Batch API for 50% cheaper embeddings
- Cost: $0.01/1M tokens (vs $0.02/1M for sync)
- Time: 24 hours max
- No rate limits

Process:
1. Read all products from Supabase (where embedding IS NULL)
2. Create batch file (JSONL format)
3. Upload batch to OpenAI
4. Wait for completion (check status)
5. Download results
6. Update Supabase with embeddings

Cost for 461K products: ~$9 (vs $18 sync)
"""

import os
import json
import time
import psycopg2
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}


def fetch_products_needing_embeddings(regenerate_all=False):
    """
    Fetch products needing embeddings

    Args:
        regenerate_all: If True, fetch ALL products (regenerate embeddings)
                       If False, only fetch products with NULL embeddings
    """
    print("\n📦 Fetching products needing embeddings...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    if regenerate_all:
        print("   🔄 Mode: REGENERATE ALL (including existing embeddings)\n")
        cur.execute("""
            SELECT product_id_internal, embedding_text
            FROM products
            WHERE embedding_text IS NOT NULL
            ORDER BY product_id_internal
        """)
    else:
        print("   ➕ Mode: NEW ONLY (NULL embeddings)\n")
        cur.execute("""
            SELECT product_id_internal, embedding_text
            FROM products
            WHERE embedding IS NULL AND embedding_text IS NOT NULL
            ORDER BY product_id_internal
        """)

    products = cur.fetchall()
    cur.close()
    conn.close()

    print(f"   ✅ Found {len(products):,} products\n")
    return products


def create_batch_file(products, filename='batch_input.jsonl'):
    """Create JSONL batch file for OpenAI"""
    print(f"📝 Creating batch file: {filename}")

    with open(filename, 'w') as f:
        for product_id, embedding_text in products:
            request = {
                "custom_id": str(product_id),
                "method": "POST",
                "url": "/v1/embeddings",
                "body": {
                    "model": "text-embedding-3-small",
                    "input": embedding_text
                }
            }
            f.write(json.dumps(request) + '\n')

    print(f"   ✅ Created {filename} with {len(products):,} requests\n")
    return filename


def upload_batch(filename):
    """Upload batch file to OpenAI"""
    print(f"📤 Uploading {filename} to OpenAI...")

    with open(filename, 'rb') as f:
        batch_file = client.files.create(
            file=f,
            purpose='batch'
        )

    print(f"   ✅ Uploaded: {batch_file.id}\n")

    print("🚀 Creating batch job...")
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/embeddings",
        completion_window="24h"
    )

    print(f"   ✅ Batch created: {batch.id}")
    print(f"   📊 Status: {batch.status}")
    print(f"   ⏱️  Estimated completion: 24 hours\n")

    return batch.id


def check_batch_status(batch_id):
    """Check status of batch job"""
    batch = client.batches.retrieve(batch_id)

    print(f"\n📊 Batch Status: {batch.status}")
    print(f"   Total requests: {batch.request_counts.total}")
    print(f"   Completed: {batch.request_counts.completed}")
    print(f"   Failed: {batch.request_counts.failed}")

    if batch.status == 'completed':
        print(f"   ✅ Output file: {batch.output_file_id}\n")
        return batch.output_file_id
    elif batch.status == 'failed':
        print(f"   ❌ Batch failed\n")
        return None
    else:
        print(f"   ⏳ Still processing...\n")
        return None


def download_results(output_file_id, filename='batch_output.jsonl'):
    """Download batch results"""
    print(f"📥 Downloading results...")

    content = client.files.content(output_file_id)

    with open(filename, 'wb') as f:
        f.write(content.read())

    print(f"   ✅ Downloaded: {filename}\n")
    return filename


def update_supabase_with_embeddings(results_file):
    """Update Supabase products with embeddings from batch results"""
    print("💾 Updating Supabase with embeddings...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    updated = 0
    failed = 0

    with open(results_file, 'r') as f:
        for line in f:
            result = json.loads(line)

            if result.get('error'):
                failed += 1
                continue

            product_id = int(result['custom_id'])
            embedding = result['response']['body']['data'][0]['embedding']

            cur.execute("""
                UPDATE products
                SET embedding = %s::vector
                WHERE product_id_internal = %s
            """, (embedding, product_id))

            updated += 1

            if updated % 1000 == 0:
                conn.commit()
                print(f"   Progress: {updated:,} updated")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\n✅ Updated {updated:,} products")
    print(f"❌ Failed {failed:,} products\n")

    return updated, failed


def main():
    print("\n" + "="*80)
    print("BATCH EMBEDDINGS GENERATION")
    print("="*80)

    print("\n📋 This script will:")
    print("1. Fetch products needing embeddings")
    print("2. Create batch file")
    print("3. Upload to OpenAI Batch API")
    print("4. Wait for completion (up to 24 hours)")
    print("5. Download and update Supabase")
    print("\n💰 Cost: 50% cheaper than sync API")
    print("⏱️  Time: Up to 24 hours")
    print("\n" + "="*80 + "\n")

    # Check if we're resuming from a previous batch
    if os.path.exists('batch_id.txt'):
        with open('batch_id.txt', 'r') as f:
            batch_id = f.read().strip()

        print(f"🔄 Found existing batch ID: {batch_id}")
        print("   Checking status...\n")

        output_file_id = check_batch_status(batch_id)

        if output_file_id:
            # Download and process results
            results_file = download_results(output_file_id)
            update_supabase_with_embeddings(results_file)

            # Cleanup
            os.remove('batch_id.txt')
            print("✅ Batch processing complete!\n")
        else:
            print("⏳ Batch still processing. Run this script again later to check status.\n")

        return

    # Start new batch
    print("Start new batch?")
    print("  1 = New embeddings only (NULL embeddings)")
    print("  2 = Regenerate ALL (including existing)")
    response = input("Choice (1/2): ")

    if response not in ['1', '2']:
        print("❌ Cancelled")
        return

    regenerate_all = (response == '2')

    # Fetch products
    products = fetch_products_needing_embeddings(regenerate_all=regenerate_all)

    if not products:
        print("✅ No products need embeddings!")
        return

    # Estimate cost
    total_tokens = len(products) * 10  # ~10 tokens per product
    cost = total_tokens / 1_000_000 * 0.01  # $0.01 per 1M tokens

    print(f"💰 Estimated cost: ${cost:.2f}")
    print(f"📊 Total products: {len(products):,}")
    print(f"⏱️  Estimated time: 24 hours max\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    # Create batch file
    batch_file = create_batch_file(products)

    # Upload to OpenAI
    batch_id = upload_batch(batch_file)

    # Save batch ID for later
    with open('batch_id.txt', 'w') as f:
        f.write(batch_id)

    print("💡 Batch submitted! Run this script again later to check status and download results.")
    print(f"   Batch ID saved to: batch_id.txt\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
