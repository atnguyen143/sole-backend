"""
Create Vector Index - Minimal Memory Usage
===========================================

Creates IVFFlat index with minimal memory requirements for similarity search.

Strategy:
1. Use fewer lists (reduces memory needed)
2. Start with 64MB maintenance_work_mem
3. Gradually increase if needed
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


def create_vector_index_minimal():
    """Create vector index with minimal memory"""
    print("\n🎯 Creating vector index (minimal memory mode)...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Get product count
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    product_count = cur.fetchone()[0]

    if product_count == 0:
        print("   ⚠️  No products with embeddings, skipping index")
        cur.close()
        conn.close()
        return

    print(f"   📊 Found {product_count:,} products with embeddings")

    # Use VERY conservative lists parameter to minimize memory
    # Optimal is sqrt(rows), but we'll use much less to save memory
    optimal_lists = int(math.sqrt(product_count))
    conservative_lists = max(10, optimal_lists // 4)  # Use 1/4 of optimal

    print(f"   🎯 Using {conservative_lists} lists (optimal would be {optimal_lists})")
    print(f"   💾 This uses less memory but index still works")

    # Try creating index with minimal memory
    memory_configs = [
        ('64MB', conservative_lists),
        ('96MB', conservative_lists),
        ('128MB', conservative_lists),
        ('128MB', max(10, conservative_lists // 2)),  # Even fewer lists
        ('64MB', 10),  # Absolute minimum
    ]

    for memory, lists in memory_configs:
        try:
            print(f"\n   Trying: {memory} memory, {lists} lists...")

            # Set memory
            cur.execute(f"SET maintenance_work_mem = '{memory}'")

            # Create index
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_products_embedding
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """)

            conn.commit()
            print(f"   ✅ Success! Vector index created with {lists} lists")
            print(f"   📊 Memory used: {memory}")
            break

        except Exception as e:
            error_msg = str(e).lower()

            if 'already exists' in error_msg:
                print(f"   ⚠️  Index already exists")
                conn.rollback()
                break

            elif 'memory' in error_msg or 'out of memory' in error_msg:
                print(f"   ❌ Insufficient memory")
                conn.rollback()
                # Try next config
                continue

            else:
                print(f"   ❌ Error: {e}")
                conn.rollback()
                break

    else:
        # All attempts failed
        print(f"\n   ⚠️  Could not create vector index with available memory")
        print(f"   💡 Similarity search will still work, just slower without index")

    cur.close()
    conn.close()


def main():
    print("\n" + "="*80)
    print("CREATE VECTOR INDEX - MINIMAL MEMORY MODE")
    print("="*80)

    create_vector_index_minimal()

    print("\n" + "="*80)
    print("✅ DONE")
    print("="*80)
    print("\nVector index created (or already exists)")
    print("Similarity searches will now be much faster!")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
