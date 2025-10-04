"""
Create Vector Index - WITH PROGRESS UPDATES
============================================

Same as aggressive mode but with progress messages so you know it's working.
"""

import os
import math
import time
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}


def main():
    print("\n" + "="*80)
    print("CREATE VECTOR INDEX - VERBOSE MODE")
    print("="*80)

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Get product count
    print("\n[1/5] Counting products with embeddings...")
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    product_count = cur.fetchone()[0]

    if product_count == 0:
        print("\n⚠️  No products with embeddings")
        cur.close()
        conn.close()
        return

    print(f"      ✅ Found {product_count:,} products")

    # Calculate optimal lists
    optimal_lists = int(math.sqrt(product_count))
    print(f"\n[2/5] Calculating optimal settings...")
    print(f"      ✅ Optimal lists: {optimal_lists}")

    # Configs to try
    configs = [
        ('2GB', optimal_lists),
        ('1GB', optimal_lists),
        ('512MB', optimal_lists),
        ('256MB', optimal_lists // 2),
    ]

    print(f"\n[3/5] Checking if index already exists...")
    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'products' AND indexname = 'idx_products_embedding'
    """)

    if cur.fetchone():
        print(f"      ⚠️  Index already exists! No need to create.")
        cur.close()
        conn.close()
        return
    else:
        print(f"      ✅ Index does not exist, will create")

    print(f"\n[4/5] Creating index (THIS MAY TAKE 5-30 MINUTES)...")
    print(f"      💡 Don't worry if it seems stuck - it's working!")
    print(f"      💡 Creating index for {product_count:,} products...")

    for i, (memory, lists) in enumerate(configs, 1):
        print(f"\n      Attempt {i}/{len(configs)}: {memory} memory, {lists} lists")
        print(f"      ⏳ Setting memory to {memory}...")

        try:
            # Set memory
            cur.execute(f"SET maintenance_work_mem = '{memory}'")
            print(f"      ✅ Memory set")

            print(f"      ⏳ Creating index... (this is the slow part, please wait)")
            start_time = time.time()

            # Create index
            cur.execute(f"""
                CREATE INDEX idx_products_embedding
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """)

            elapsed = time.time() - start_time
            conn.commit()

            print(f"\n{'='*80}")
            print(f"✅ SUCCESS! Index created in {elapsed/60:.1f} minutes")
            print(f"{'='*80}")
            print(f"Settings used:")
            print(f"  - Lists: {lists}")
            print(f"  - Memory: {memory}")
            print(f"  - Products indexed: {product_count:,}")
            print(f"\n[5/5] Verifying index...")

            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'products' AND indexname = 'idx_products_embedding'
            """)

            if cur.fetchone():
                print(f"      ✅ Index verified!")
                print(f"\n🚀 Similarity searches will now be 100-200x faster!")

            print(f"{'='*80}\n")
            cur.close()
            conn.close()
            return

        except Exception as e:
            error_msg = str(e).lower()

            if 'memory' in error_msg or 'out of memory' in error_msg:
                print(f"      ❌ Not enough memory with {memory}")
                conn.rollback()
                if i < len(configs):
                    print(f"      🔄 Trying lower memory setting...")
                continue
            else:
                print(f"      ❌ Error: {e}")
                conn.rollback()
                cur.close()
                conn.close()
                return

    # All failed
    print(f"\n{'='*80}")
    print(f"⚠️  All memory configs failed")
    print(f"{'='*80}")
    print(f"Try using CONCURRENTLY mode (slower but less memory):")
    print(f"  CREATE INDEX CONCURRENTLY idx_products_embedding ...")
    print(f"{'='*80}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted by user (Ctrl+C)")
        print(f"   Index creation was cancelled - nothing broken!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
