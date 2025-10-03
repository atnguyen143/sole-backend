"""
Create vector and standard indexes on products table
Run this after migration completes
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Configuration
SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_DATABASE = os.getenv("SUPABASE_DATABASE", "postgres")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD")
SUPABASE_PORT = os.getenv("SUPABASE_PORT", "5432")


def get_supabase_connection():
    """Create Supabase connection"""
    conn_string = f"postgresql://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DATABASE}"
    return psycopg2.connect(conn_string)


def create_indexes():
    """Create all indexes for products table"""
    conn = get_supabase_connection()
    conn.autocommit = True  # Required for CREATE INDEX CONCURRENTLY
    cursor = conn.cursor()

    print("\n🔨 Creating indexes on products table...\n")

    # Check product count first
    cursor.execute("SELECT COUNT(*) FROM products")
    product_count = cursor.fetchone()[0]
    print(f"📊 Total products in table: {product_count:,}\n")

    # Determine optimal lists parameter based on product count
    if product_count < 10000:
        lists = 50
    elif product_count < 100000:
        lists = 100
    elif product_count < 500000:
        lists = 500
    else:
        lists = 1000

    print(f"🎯 Using lists = {lists} for IVFFlat index (optimal for {product_count:,} products)\n")

    indexes = [
        {
            "name": "products_embedding_idx",
            "sql": f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS products_embedding_idx
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """,
            "description": "Vector similarity index (IVFFlat)"
        },
        {
            "name": "products_platform_idx",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS products_platform_idx
                ON products(platform)
            """,
            "description": "Platform filter index"
        },
        {
            "name": "products_style_id_normalized_idx",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS products_style_id_normalized_idx
                ON products(style_id_normalized)
            """,
            "description": "Style ID lookup index"
        },
        {
            "name": "products_keyword_idx",
            "sql": """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS products_keyword_idx
                ON products(keyword_used)
            """,
            "description": "Keyword filter index"
        }
    ]

    for idx in indexes:
        try:
            print(f"🔨 Creating {idx['name']}... ({idx['description']})")
            cursor.execute(idx["sql"])
            print(f"   ✅ {idx['name']} created successfully\n")
        except Exception as e:
            if "already exists" in str(e):
                print(f"   ⚠️  {idx['name']} already exists, skipping\n")
            else:
                print(f"   ❌ Error creating {idx['name']}: {e}\n")

    # Verify indexes
    print("\n📋 Verifying indexes on products table:\n")
    cursor.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'products'
        ORDER BY indexname
    """)

    indexes = cursor.fetchall()
    for idx_name, idx_def in indexes:
        print(f"   ✓ {idx_name}")

    print(f"\n✅ Index creation complete! Total indexes: {len(indexes)}\n")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    try:
        create_indexes()
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
