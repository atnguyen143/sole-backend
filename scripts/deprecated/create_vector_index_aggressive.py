"""
Create Vector Index - Try High Memory First
============================================

Attempts to use high memory settings for optimal index creation.
The memory is only needed during creation, not for using the index.

Falls back to lower settings if high memory fails.
"""

import os
import math
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
    print("CREATE VECTOR INDEX - AGGRESSIVE MODE (HIGH MEMORY)")
    print("="*80)

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Get product count
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    product_count = cur.fetchone()[0]

    if product_count == 0:
        print("\n⚠️  No products with embeddings")
        cur.close()
        conn.close()
        return

    print(f"\n📊 Products with embeddings: {product_count:,}")

    # Calculate optimal lists
    optimal_lists = int(math.sqrt(product_count))
    print(f"🎯 Optimal lists parameter: {optimal_lists}")

    # Try different configs (high memory first, fall back if needed)
    configs = [
        ('2GB', optimal_lists),
        ('1GB', optimal_lists),
        ('512MB', optimal_lists),
        ('256MB', optimal_lists),
        ('256MB', optimal_lists // 2),
        ('128MB', optimal_lists // 4),
        ('64MB', 10),
    ]

    print(f"\n💡 Memory is only needed during index creation (temporary)")
    print(f"💡 After creation, the index uses minimal memory\n")

    for memory, lists in configs:
        try:
            print(f"Attempting: {memory} memory, {lists} lists...")

            # Set high memory for this session (temporary)
            cur.execute(f"SET maintenance_work_mem = '{memory}'")

            # Create index
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_products_embedding
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """)

            conn.commit()

            print(f"\n{'='*80}")
            print(f"✅ SUCCESS!")
            print(f"{'='*80}")
            print(f"Vector index created with:")
            print(f"  - Lists: {lists}")
            print(f"  - Memory used: {memory}")
            print(f"\nSimilarity searches will now be 100-200x faster!")
            print(f"{'='*80}\n")

            cur.close()
            conn.close()
            return

        except Exception as e:
            error_msg = str(e).lower()

            if 'already exists' in error_msg:
                print(f"⚠️  Index already exists\n")
                conn.rollback()
                cur.close()
                conn.close()
                return

            elif 'memory' in error_msg or 'out of memory' in error_msg:
                print(f"❌ Insufficient memory ({memory})")
                conn.rollback()
                # Try next config
                continue

            else:
                print(f"❌ Error: {e}\n")
                conn.rollback()
                cur.close()
                conn.close()
                return

    # All configs failed
    print(f"\n{'='*80}")
    print(f"⚠️  ALL ATTEMPTS FAILED")
    print(f"{'='*80}")
    print(f"Could not create vector index with available memory.")
    print(f"Similarity searches will still work, just slower (no index).")
    print(f"\n💡 Contact Supabase support to increase maintenance_work_mem limit")
    print(f"{'='*80}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
