"""
CREATE HNSW INDEX FOR PRODUCT EMBEDDINGS
=========================================

Creates optimized HNSW index for vector similarity search.
Two modes:
1. Max performance (3.5GB RAM) - Best quality, use when nothing else running
2. Conservative (default settings) - Safer, can run alongside other operations

Requirements:
- All embeddings must be inserted first
- Best to run when Supabase has minimal activity
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DB'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': os.getenv('SUPABASE_PORT', '5432')
}


def drop_existing_index():
    """Drop existing index if it exists"""
    print("🗑️  Checking for existing index...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    # Set long timeout for index operations
    conn.autocommit = True
    cur = conn.cursor()

    # Check if index exists
    cur.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'products'
        AND indexname = 'products_embedding_idx'
    """)

    if cur.fetchone():
        print("   ⚠️  Found existing index: products_embedding_idx")
        print("   🗑️  Dropping index...")

        cur.execute("DROP INDEX CONCURRENTLY IF EXISTS products_embedding_idx")

        print("   ✅ Index dropped\n")
    else:
        print("   ✅ No existing index found\n")

    cur.close()
    conn.close()


def create_index_max_performance():
    """Create HNSW index with maximum performance settings (3.5GB RAM)"""
    print("\n" + "="*80)
    print("CREATING HNSW INDEX - MAX PERFORMANCE MODE")
    print("="*80)
    print("⚙️  Settings:")
    print("   - maintenance_work_mem: 3.5GB")
    print("   - max_parallel_maintenance_workers: 4")
    print("   - m: 32 (high quality)")
    print("   - ef_construction: 200 (high accuracy)")
    print("\n⚠️  WARNING: This will use almost all available RAM (4GB)")
    print("⏱️  Estimated time: 10-30 minutes for 461K products\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # Set statement timeout to unlimited
        print("📝 Setting statement timeout to unlimited...")
        cur.execute("SET statement_timeout = '0'")

        # Max out maintenance memory
        print("📝 Setting maintenance_work_mem to 3.5GB...")
        cur.execute("SET maintenance_work_mem = '3.5GB'")

        # Enable parallel workers
        print("📝 Setting max_parallel_maintenance_workers to 4...")
        cur.execute("SET max_parallel_maintenance_workers = 4")

        # Create index
        print("\n🚀 Creating HNSW index...")
        print("   (This will take a while - don't interrupt!)\n")

        cur.execute("""
            CREATE INDEX CONCURRENTLY products_embedding_idx
            ON products
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 32, ef_construction = 200)
        """)

        print("\n✅ Index created successfully!")

        # Reset settings
        print("📝 Resetting settings to default...")
        cur.execute("RESET maintenance_work_mem")
        cur.execute("RESET max_parallel_maintenance_workers")

        print("✅ Settings reset\n")

    except Exception as e:
        print(f"\n❌ Error creating index: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def create_index_conservative():
    """Create HNSW index with conservative settings (default RAM)"""
    print("\n" + "="*80)
    print("CREATING HNSW INDEX - CONSERVATIVE MODE")
    print("="*80)
    print("⚙️  Settings:")
    print("   - maintenance_work_mem: default")
    print("   - m: 16 (standard quality)")
    print("   - ef_construction: 64 (standard accuracy)")
    print("\n⏱️  Estimated time: 15-45 minutes for 461K products\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # Set statement timeout to unlimited
        print("📝 Setting statement timeout to unlimited...")
        cur.execute("SET statement_timeout = '0'")

        # Create index
        print("\n🚀 Creating HNSW index...")
        print("   (This will take a while - don't interrupt!)\n")

        cur.execute("""
            CREATE INDEX CONCURRENTLY products_embedding_idx
            ON products
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """)

        print("\n✅ Index created successfully!\n")

    except Exception as e:
        print(f"\n❌ Error creating index: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def check_index_status():
    """Check if index exists and its status"""
    print("\n📊 Checking index status...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Check for index
    cur.execute("""
        SELECT
            indexname,
            indexdef
        FROM pg_indexes
        WHERE tablename = 'products'
        AND indexname = 'products_embedding_idx'
    """)

    result = cur.fetchone()

    if result:
        print(f"\n✅ Index exists: {result[0]}")
        print(f"   Definition: {result[1]}\n")
    else:
        print("\n❌ No index found\n")

    # Check for any invalid indexes
    cur.execute("""
        SELECT
            indexname,
            pg_size_pretty(pg_relation_size(indexname::regclass)) as size
        FROM pg_indexes
        WHERE tablename = 'products'
    """)

    indexes = cur.fetchall()

    if indexes:
        print("📋 All indexes on products table:")
        for idx_name, idx_size in indexes:
            print(f"   - {idx_name}: {idx_size}")
        print()

    cur.close()
    conn.close()


def main():
    print("\n" + "="*80)
    print("HNSW INDEX CREATION TOOL")
    print("="*80)
    print("\nThis script will create an HNSW index for product embeddings.")
    print("\nOptions:")
    print("  1 = Max performance (3.5GB RAM, m=32, ef_construction=200)")
    print("  2 = Conservative (default settings, m=16, ef_construction=64)")
    print("  3 = Drop existing index only")
    print("  4 = Check index status")

    choice = input("\nChoice (1/2/3/4): ").strip()

    if choice == '1':
        confirm = input("\n⚠️  Max performance mode will use 3.5GB RAM. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ Cancelled")
            return

        drop_existing_index()
        create_index_max_performance()
        check_index_status()

    elif choice == '2':
        drop_existing_index()
        create_index_conservative()
        check_index_status()

    elif choice == '3':
        drop_existing_index()

    elif choice == '4':
        check_index_status()

    else:
        print("❌ Invalid choice")
        return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        print("⚠️  Note: CONCURRENTLY indexes can be safely interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
