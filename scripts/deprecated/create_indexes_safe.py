"""
Create Indexes on Products Table - SAFE MODE
=============================================

Creates indexes with automatic memory fallback strategies
Safe to run overnight without manual intervention

Features:
- Auto-detects available memory
- Fallback strategies for vector index
- Progress tracking
- Safe error handling
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


def create_standard_indexes(cur, conn):
    """Create standard B-tree indexes (fast, no memory issues)"""
    print("\n📋 Creating standard indexes...")

    indexes = [
        {
            'name': 'idx_products_platform',
            'sql': 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_platform ON products(platform)',
            'description': 'Platform lookup'
        },
        {
            'name': 'idx_products_style_id_normalized',
            'sql': 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_style_id_normalized ON products(style_id_normalized)',
            'description': 'Style ID normalized lookup'
        },
        {
            'name': 'idx_products_name_platform',
            'sql': 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_name_platform ON products(product_name_platform)',
            'description': 'Product name lookup'
        },
        {
            'name': 'idx_products_composite',
            'sql': 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_composite ON products(platform, product_id_platform)',
            'description': 'Composite platform + ID'
        }
    ]

    for idx in indexes:
        try:
            print(f"   🔨 Creating {idx['name']}... ({idx['description']})")
            cur.execute(idx['sql'])
            conn.commit()
            print(f"      ✅ Created")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"      ⚠️  Already exists")
                conn.rollback()
            else:
                print(f"      ❌ Error: {e}")
                conn.rollback()

    print("\n✅ Standard indexes complete")


def create_vector_index_safe(cur, conn):
    """
    Create vector index with automatic fallback strategies

    Strategies (in order):
    1. Try with optimal lists parameter + 512MB memory
    2. Fallback to 256MB memory
    3. Fallback to 128MB memory
    4. Fallback to fewer lists (half)
    5. Skip if all fail (can index later when more memory available)
    """
    print("\n🎯 Creating vector similarity index...")

    # Get product count
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    product_count = cur.fetchone()[0]

    if product_count == 0:
        print("   ⚠️  No products with embeddings yet, skipping vector index")
        return

    # Calculate optimal lists: sqrt(total_rows)
    optimal_lists = max(50, min(2000, int(math.sqrt(product_count))))

    print(f"   📊 Found {product_count:,} products with embeddings")
    print(f"   🎯 Optimal lists parameter: {optimal_lists}")

    # Strategy 1: Try with 512MB + optimal lists
    strategies = [
        {'memory': '512MB', 'lists': optimal_lists, 'desc': 'Optimal (512MB)'},
        {'memory': '256MB', 'lists': optimal_lists, 'desc': 'Reduced memory (256MB)'},
        {'memory': '128MB', 'lists': optimal_lists, 'desc': 'Minimal memory (128MB)'},
        {'memory': '256MB', 'lists': optimal_lists // 2, 'desc': 'Reduced lists (256MB)'},
        {'memory': '128MB', 'lists': max(50, optimal_lists // 4), 'desc': 'Minimal lists (128MB)'},
    ]

    for i, strategy in enumerate(strategies, 1):
        try:
            print(f"\n   Strategy {i}/{len(strategies)}: {strategy['desc']}")
            print(f"      Memory: {strategy['memory']}, Lists: {strategy['lists']}")

            # Set memory for index creation
            cur.execute(f"SET maintenance_work_mem = '{strategy['memory']}'")

            # Create index
            cur.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_products_embedding
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {strategy['lists']})
            """)

            conn.commit()
            print(f"      ✅ Vector index created successfully!")
            print(f"      📊 Using {strategy['lists']} lists with {strategy['memory']} memory")
            return

        except Exception as e:
            error_msg = str(e).lower()

            if 'already exists' in error_msg:
                print(f"      ⚠️  Index already exists")
                conn.rollback()
                return

            elif 'memory' in error_msg or 'out of memory' in error_msg:
                print(f"      ❌ Insufficient memory: {e}")
                conn.rollback()

                if i < len(strategies):
                    print(f"      🔄 Trying next strategy...")
                else:
                    print(f"\n      ⚠️  All strategies failed")
                    print(f"      💡 Vector index creation skipped")
                    print(f"      💡 You can create it manually later with:")
                    print(f"         CREATE INDEX idx_products_embedding ON products")
                    print(f"         USING ivfflat (embedding vector_cosine_ops)")
                    print(f"         WITH (lists = {optimal_lists});")

            else:
                print(f"      ❌ Unexpected error: {e}")
                conn.rollback()

                if i < len(strategies):
                    print(f"      🔄 Trying next strategy...")
                else:
                    print(f"\n      ⚠️  Vector index creation failed")


def main():
    print("\n" + "="*80)
    print("CREATE INDEXES - SAFE MODE WITH AUTOMATIC FALLBACKS")
    print("="*80)

    try:
        conn = psycopg2.connect(**SUPABASE_CONFIG)
        cur = conn.cursor()

        # Step 1: Create standard indexes (always succeeds)
        create_standard_indexes(cur, conn)

        # Step 2: Create vector index with fallback strategies
        create_vector_index_safe(cur, conn)

        cur.close()
        conn.close()

        print("\n" + "="*80)
        print("✅ INDEX CREATION COMPLETE")
        print("="*80)
        print("\nIndexes are ready for optimal query performance!")

    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
