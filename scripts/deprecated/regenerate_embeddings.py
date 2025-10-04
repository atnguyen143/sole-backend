"""
Regenerate Embeddings for Products Table
=========================================

Regenerates embeddings based on UPPERCASE product_name_platform.
Processes in order of product_id_internal (insert order).

Speed optimizations:
- Batch processing (100 items at a time)
- Parallel embedding generation (10 concurrent threads)
- Async insertion queue
- Progress tracking

Estimated time: ~2-3 hours for 124K products
Estimated cost: ~$2.00
"""

import os
import time
from queue import Queue
from threading import Thread, Event
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
stop_event = Event()
stats = {'generated': 0, 'updated': 0, 'failed': 0}

BATCH_SIZE = 100
NUM_WORKERS = 10  # Parallel OpenAI API calls


def generate_embedding(text, retry_count=3):
    """Generate embedding with retries"""
    for attempt in range(retry_count):
        if stop_event.is_set():
            return None
        try:
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"   ❌ Failed after {retry_count} attempts: {e}")
                return None
    return None


def embedding_worker(task_queue, result_queue):
    """Worker thread to generate embeddings"""
    while not stop_event.is_set():
        try:
            task = task_queue.get(timeout=1)
            if task is None:  # Poison pill
                break

            product_id_internal, embedding_text = task
            embedding = generate_embedding(embedding_text)

            if embedding:
                result_queue.put((product_id_internal, embedding))
                stats['generated'] += 1
            else:
                stats['failed'] += 1

            task_queue.task_done()

        except Exception:
            continue


def update_worker(result_queue):
    """Worker thread to update database"""
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    while not stop_event.is_set():
        try:
            batch = []
            # Collect batch
            while len(batch) < 50:
                try:
                    result = result_queue.get(timeout=1)
                    if result is None:  # Poison pill
                        break
                    batch.append(result)
                except:
                    break

            if not batch:
                continue

            # Batch update
            for product_id_internal, embedding in batch:
                cur.execute("""
                    UPDATE products
                    SET embedding = %s::vector
                    WHERE product_id_internal = %s
                """, (embedding, product_id_internal))
                stats['updated'] += 1

            conn.commit()

        except Exception as e:
            print(f"   ❌ Update error: {e}")
            conn.rollback()

    cur.close()
    conn.close()


def main():
    print("\n" + "="*80)
    print("REGENERATE EMBEDDINGS FOR PRODUCTS TABLE")
    print("="*80)
    print("\n⚡ Speed optimizations:")
    print(f"   - Batch size: {BATCH_SIZE}")
    print(f"   - Parallel workers: {NUM_WORKERS}")
    print(f"   - Model: text-embedding-3-small")

    # Fetch all products that need embedding regeneration
    print("\n📊 Fetching products...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            product_id_internal,
            product_name_platform
        FROM products
        ORDER BY product_id_internal
    """)

    products = cur.fetchall()
    total = len(products)

    print(f"   ✅ Found {total:,} products to process")
    print(f"\n💰 Estimated cost: ${total * 0.02 / 1000000:.2f}")
    print(f"⏱️  Estimated time: {total / 1000:.1f} minutes\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    # Setup queues and workers
    task_queue = Queue(maxsize=500)
    result_queue = Queue(maxsize=500)

    # Start embedding workers
    workers = []
    for i in range(NUM_WORKERS):
        worker = Thread(target=embedding_worker, args=(task_queue, result_queue), daemon=True)
        worker.start()
        workers.append(worker)

    # Start update worker
    updater = Thread(target=update_worker, args=(result_queue,), daemon=True)
    updater.start()

    # Process products
    print(f"\n🚀 Processing {total:,} products...\n")
    start_time = time.time()

    for i, (product_id_internal, product_name) in enumerate(products, 1):
        if stop_event.is_set():
            break

        # Use UPPERCASE name for embedding (matching current state)
        embedding_text = product_name.upper() if product_name else ""
        task_queue.put((product_id_internal, embedding_text))

        # Progress update
        if i % 1000 == 0 or i == total:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (total - i) / rate if rate > 0 else 0

            print(f"   Progress: {i:,}/{total:,} ({i/total*100:.1f}%)")
            print(f"   Generated: {stats['generated']:,} | Updated: {stats['updated']:,} | Failed: {stats['failed']}")
            print(f"   Rate: {rate:.1f} products/sec | ETA: {eta/60:.1f} min\n")

    # Wait for completion
    print("⏳ Waiting for workers to finish...")
    task_queue.join()

    # Stop workers
    for _ in range(NUM_WORKERS):
        task_queue.put(None)
    for worker in workers:
        worker.join()

    result_queue.put(None)
    updater.join()

    # Final stats
    elapsed = time.time() - start_time
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"✅ Generated:  {stats['generated']:,}")
    print(f"✅ Updated:    {stats['updated']:,}")
    print(f"❌ Failed:     {stats['failed']:,}")
    print(f"\n⏱️  Total time: {elapsed/60:.1f} minutes")
    print(f"⚡ Rate: {total/elapsed:.1f} products/sec")

    cur.close()
    conn.close()

    print("\n✅ Embedding regeneration complete!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopping...")
        stop_event.set()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
