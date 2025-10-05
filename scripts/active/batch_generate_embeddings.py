"""
BATCH EMBEDDINGS GENERATION
============================

Uses OpenAI Batch API for 50% cheaper embeddings
- Cost: $0.01/1M tokens (vs $0.02/1M for sync)
- Time: 24 hours max
- No rate limits

Process:
1. Update all products with fresh embedding_text (lowercase, normalized)
2. Create batch file (JSONL format)
3. Upload batch to OpenAI
4. Wait for completion (check status)
5. Download results
6. Update Supabase with embeddings

Cost for 461K products: ~$9 (vs $18 sync)
"""

import os
import re
import json
import time
import psycopg2
import psycopg2.extras
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


def normalize_text_for_embedding(text):
    """Normalize text for embeddings (lowercase, case insensitive)"""
    if not text:
        return ""

    # Expand abbreviations first (before removing punctuation)
    text = re.sub(r'\bWmns\b', 'womens', text, flags=re.IGNORECASE)
    text = re.sub(r'\(W\)', 'womens', text, flags=re.IGNORECASE)

    # Remove parentheses, single quotes, hyphens, underscores
    text = text.replace('(', '').replace(')', '').replace("'", '').replace('-', ' ').replace('_', ' ')

    # Lowercase everything for case-insensitive matching
    text = text.lower()

    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_embedding_text(name, style_id=None):
    """
    Generate embedding text with delimiter (works for both StockX and Alias)
    Format: "{normalized_style} | {name}" (pipe delimiter separates style from name)

    Examples:
    - style_id="DD0385-100", name="Air Max 90 'Cork'" → "dd0385100 | air max 90 cork"
    - style_id="DD0385-100/DD0385-200", name="Air Max 90" → "dd0385100 dd0385200 | air max 90"
    - No style_id, name="Air Max 90" → "air max 90"
    """
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if style_id:
        # Remove spaces, dashes, underscores first
        normalized_style = style_id.replace(' ', '').replace('-', '').replace('_', '')
        # THEN replace slashes with spaces (for multi-SKU products)
        normalized_style = normalized_style.replace('/', ' ').lower()
        return f"{normalized_style} | {normalized_name}".strip()

    return normalized_name


def update_all_embedding_texts():
    """Update embedding_text for ALL products with normalized format"""
    print("\n🔄 Updating embedding_text for all products...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Fetch all products
    cur.execute("""
        SELECT product_id_internal, product_name_platform, style_id_platform
        FROM products
    """)

    products = cur.fetchall()
    total = len(products)
    print(f"   ✅ Found {total:,} products to update\n")

    # Update in batches
    batch_size = 1000
    updated = 0

    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]

        for product_id, name, style_id in batch:
            embedding_text = generate_embedding_text(name, style_id)

            cur.execute("""
                UPDATE products
                SET embedding_text = %s
                WHERE product_id_internal = %s
            """, (embedding_text, product_id))

        conn.commit()
        updated += len(batch)
        print(f"   Progress: {updated:,}/{total:,} ({updated/total*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n✅ Updated {updated:,} embedding_text values\n")
    return updated


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


def create_batch_file(products, batch_num=1, filename_prefix='batch_input'):
    """Create JSONL batch file for OpenAI (max 50K products per file)"""
    filename = f"{filename_prefix}_{batch_num}.jsonl"
    print(f"📝 Creating batch file {batch_num}: {filename}")

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


def upload_batch(filename, batch_num=1):
    """Upload batch file to OpenAI"""
    print(f"📤 Uploading batch {batch_num}: {filename}...")

    with open(filename, 'rb') as f:
        batch_file = client.files.create(
            file=f,
            purpose='batch'
        )

    print(f"   ✅ Uploaded: {batch_file.id}\n")

    print(f"🚀 Creating batch job {batch_num}...")
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/embeddings",
        completion_window="24h"
    )

    print(f"   ✅ Batch {batch_num} created: {batch.id}")
    print(f"   📊 Status: {batch.status}")
    print(f"   ⏱️  Estimated completion: 24 hours\n")

    return batch.id


def check_batch_status(batch_id):
    """Check status of batch job - returns ('status', output_file_id or None)"""
    batch = client.batches.retrieve(batch_id)

    print(f"\n📊 Batch Status: {batch.status}")
    print(f"   Total requests: {batch.request_counts.total}")
    print(f"   Completed: {batch.request_counts.completed}")
    print(f"   Failed: {batch.request_counts.failed}")

    if batch.status == 'completed':
        print(f"   ✅ Output file: {batch.output_file_id}\n")
        return ('completed', batch.output_file_id)
    elif batch.status == 'failed':
        print(f"   ❌ Batch failed\n")
        return ('failed', None)
    else:
        print(f"   ⏳ Still processing...\n")
        return (batch.status, None)


def download_results(output_file_id, filename='batch_output.jsonl'):
    """Download batch results (skip if already downloaded)"""

    # Check if file already exists
    if os.path.exists(filename):
        print(f"📥 Results file already exists: {filename}")
        print(f"   ⏭️  Skipping download\n")
        return filename

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
    batch_updates = []
    BATCH_SIZE = 5000  # Increased from 1000

    with open(results_file, 'r') as f:
        for line in f:
            result = json.loads(line)

            if result.get('error'):
                failed += 1
                continue

            product_id = int(result['custom_id'])
            embedding = result['response']['body']['data'][0]['embedding']
            batch_updates.append((embedding, product_id))

            # Batch update every 5000 records
            if len(batch_updates) >= BATCH_SIZE:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    UPDATE products
                    SET embedding = updates.embedding::vector
                    FROM (VALUES %s) AS updates(embedding, product_id)
                    WHERE products.product_id_internal = updates.product_id::integer
                    """,
                    batch_updates
                )
                conn.commit()
                updated += len(batch_updates)
                print(f"   Progress: {updated:,} updated")
                batch_updates = []

    # Insert remaining records
    if batch_updates:
        psycopg2.extras.execute_values(
            cur,
            """
            UPDATE products
            SET embedding = updates.embedding::vector
            FROM (VALUES %s) AS updates(embedding, product_id)
            WHERE products.product_id_internal = updates.product_id::integer
            """,
            batch_updates
        )
        conn.commit()
        updated += len(batch_updates)

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
    print("2. Split into multiple batches (50K limit per batch)")
    print("3. Upload all batches to OpenAI Batch API")
    print("4. Wait for completion (up to 24 hours)")
    print("5. Download and update Supabase")
    print("\n💰 Cost: 50% cheaper than sync API")
    print("⏱️  Time: Up to 24 hours")
    print("\n" + "="*80 + "\n")

    # Check if we're resuming from previous batches
    if os.path.exists('batch_ids.json'):
        with open('batch_ids.json', 'r') as f:
            batch_data = json.load(f)
            batch_ids = batch_data['batch_ids']
            total_batches = batch_data['total_batches']

        print(f"🔄 Found {len(batch_ids)} existing batch IDs")
        print("   Checking status of all batches...\n")

        all_completed = True
        output_files = []
        failed_batches = []

        for i, batch_id in enumerate(batch_ids, 1):
            print(f"📊 Batch {i}/{total_batches}: {batch_id}")
            status, output_file_id = check_batch_status(batch_id)

            if status == 'completed':
                output_files.append((i, output_file_id))
            elif status == 'failed':
                failed_batches.append(i)
                all_completed = False
            else:
                all_completed = False

        # Show summary
        print(f"\n{'='*80}")
        print("BATCH STATUS SUMMARY")
        print(f"{'='*80}")
        print(f"✅ Completed: {len(output_files)}/{total_batches}")
        print(f"❌ Failed: {len(failed_batches)}/{total_batches}")
        print(f"⏳ Processing: {total_batches - len(output_files) - len(failed_batches)}/{total_batches}")

        if failed_batches:
            print(f"\n❌ Failed batch numbers: {failed_batches}")
            print(f"\n🔧 Want to resubmit failed batches?")
            print(f"   y = Resubmit {len(failed_batches)} failed batches now")
            print(f"   n = Skip (check again later)")
            response = input("Choice (y/n): ")

            if response.lower() == 'y':
                # Fetch products for failed batches
                products = fetch_products_needing_embeddings(regenerate_all=False)

                if not products:
                    print("✅ No products need embeddings!")
                    return

                BATCH_SIZE_LIMIT = 50000
                new_batch_ids = []

                # Resubmit only failed batches
                for batch_num in failed_batches:
                    start_idx = (batch_num - 1) * BATCH_SIZE_LIMIT
                    end_idx = min(batch_num * BATCH_SIZE_LIMIT, len(products))

                    if start_idx >= len(products):
                        print(f"⚠️  Batch {batch_num} out of range, skipping")
                        continue

                    batch_products = products[start_idx:end_idx]

                    print(f"\n{'='*80}")
                    print(f"Resubmitting Batch {batch_num}/{total_batches}")
                    print(f"Products: {start_idx:,} to {end_idx:,} ({len(batch_products):,} items)")
                    print(f"{'='*80}\n")

                    # Create batch file
                    batch_file = create_batch_file(batch_products, batch_num=batch_num)

                    # Upload to OpenAI
                    new_batch_id = upload_batch(batch_file, batch_num=batch_num)
                    new_batch_ids.append(new_batch_id)

                    # Update batch_ids.json with new ID
                    batch_ids[batch_num - 1] = new_batch_id

                    # Add 20 min delay before last failed batch (if multiple)
                    if len(failed_batches) > 1 and batch_num == failed_batches[-2]:
                        print(f"\n⏰ Waiting 20 minutes before submitting final failed batch...")
                        print(f"   Started at: {time.strftime('%I:%M:%S %p')}")

                        for remaining in range(1200, 0, -60):
                            mins = remaining // 60
                            print(f"   ⏳ {mins} minutes remaining...", end='\r')
                            time.sleep(60)

                        print(f"\n   ✅ Wait complete! Submitting final batch...")
                        print(f"   Current time: {time.strftime('%I:%M:%S %p')}\n")

                # Save updated batch IDs
                with open('batch_ids.json', 'w') as f:
                    json.dump({
                        'batch_ids': batch_ids,
                        'total_batches': total_batches
                    }, f, indent=2)

                print(f"\n✅ Resubmitted {len(new_batch_ids)} failed batches!")
                print(f"💾 Updated batch_ids.json\n")
                return

        if all_completed and len(output_files) == len(batch_ids):
            # Download and process all results
            print(f"\n✅ All {total_batches} batches completed! Downloading results...\n")

            all_results = []
            for batch_num, output_file_id in output_files:
                results_file = download_results(output_file_id, filename=f'batch_output_{batch_num}.jsonl')
                all_results.append(results_file)

            # Update Supabase with all results
            total_updated = 0
            total_failed = 0

            for results_file in all_results:
                updated, failed = update_supabase_with_embeddings(results_file)
                total_updated += updated
                total_failed += failed

            print(f"\n{'='*80}")
            print("FINAL RESULTS - ALL BATCHES")
            print(f"{'='*80}")
            print(f"✅ Total updated: {total_updated:,}")
            print(f"❌ Total failed: {total_failed:,}")
            print(f"📊 Batches processed: {total_batches}")

            # Cleanup


            print("\n✅ All batch processing complete!\n")
        else:
            print(f"\n⏳ Run this script again later to check status.\n")

        return

    # Ask if they want to update embedding_text
    print("Update embedding_text first?")
    print("  y = Update all embedding_text (normalized, lowercase)")
    print("  n = Skip (already updated)")
    response = input("Choice (y/n): ")

    if response.lower() == 'y':
        update_all_embedding_texts()

    # Start new batch
    print("\nGenerate embeddings for:")
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

    # Calculate number of batches needed (50K limit per batch)
    BATCH_SIZE_LIMIT = 50000
    num_batches = (len(products) + BATCH_SIZE_LIMIT - 1) // BATCH_SIZE_LIMIT

    # Estimate cost
    total_tokens = len(products) * 10  # ~10 tokens per product
    cost = total_tokens / 1_000_000 * 0.01  # $0.01 per 1M tokens

    print(f"💰 Estimated cost: ${cost:.2f}")
    print(f"📊 Total products: {len(products):,}")
    print(f"📦 Number of batches: {num_batches}")
    print(f"⏱️  Estimated time: 24 hours max\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    # Split products into batches and upload each
    batch_ids = []

    for i in range(num_batches):
        start_idx = i * BATCH_SIZE_LIMIT
        end_idx = min((i + 1) * BATCH_SIZE_LIMIT, len(products))
        batch_products = products[start_idx:end_idx]

        print(f"\n{'='*80}")
        print(f"Processing Batch {i+1}/{num_batches}")
        print(f"Products: {start_idx:,} to {end_idx:,} ({len(batch_products):,} items)")
        print(f"{'='*80}\n")

        # Create batch file
        batch_file = create_batch_file(batch_products, batch_num=i+1)

        # Upload to OpenAI
        batch_id = upload_batch(batch_file, batch_num=i+1)
        batch_ids.append(batch_id)

        # Add 20 min delay before last batch (to avoid queue limit)
        if i == num_batches - 2:  # Second to last batch
            print(f"\n⏰ Waiting 20 minutes before submitting final batch...")
            print(f"   This prevents hitting the 3M token queue limit")
            print(f"   Started at: {time.strftime('%I:%M:%S %p')}")

            for remaining in range(1200, 0, -60):  # 20 min = 1200 seconds
                mins = remaining // 60
                print(f"   ⏳ {mins} minutes remaining...", end='\r')
                time.sleep(60)

            print(f"\n   ✅ Wait complete! Submitting final batch...")
            print(f"   Current time: {time.strftime('%I:%M:%S %p')}\n")

    # Save all batch IDs for later
    with open('batch_ids.json', 'w') as f:
        json.dump({
            'batch_ids': batch_ids,
            'total_batches': num_batches
        }, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✅ All {num_batches} batches submitted!")
    print(f"{'='*80}")
    print(f"📊 Total batch IDs: {len(batch_ids)}")
    print(f"💾 Saved to: batch_ids.json")
    print(f"\n💡 Run this script again later to check status and download results.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
