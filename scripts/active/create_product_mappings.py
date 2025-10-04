"""
Create Product Mappings (Alias → StockX)
=========================================

Automatically links alias products to their canonical StockX product using:
1. Style ID matching (if both have same normalized style ID)
2. Embedding similarity (cosine similarity > 0.85)
3. Manual review for low-confidence matches

This helps consolidate product data and improve inventory tracking.
"""

import os
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


def create_table():
    """Create product_mapping table if not exists"""
    print("\n📋 Creating product_mapping table...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    with open('sql/create_product_mapping_table.sql', 'r') as f:
        sql = f.read()
        cur.execute(sql)

    conn.commit()
    cur.close()
    conn.close()

    print("   ✅ Table created")


def map_by_style_id():
    """Map alias → stockx by matching normalized style IDs"""
    print("\n🔍 Mapping by style ID...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Find alias products with style IDs that match stockx products
    cur.execute("""
        INSERT INTO product_mapping (
            alias_product_id,
            stockx_product_id,
            confidence_score,
            mapping_method,
            created_by
        )
        SELECT
            ap.product_id_internal,
            sp.product_id_internal,
            1.00,  -- Perfect match via style ID
            'style_id_match',
            'system'
        FROM products ap
        JOIN products sp ON ap.style_id_normalized = sp.style_id_normalized
        WHERE ap.platform = 'alias'
          AND sp.platform = 'stockx'
          AND ap.style_id_normalized IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM product_mapping pm
              WHERE pm.alias_product_id = ap.product_id_internal
          )
        ON CONFLICT (alias_product_id) DO NOTHING
    """)

    count = cur.rowcount
    conn.commit()

    print(f"   ✅ Mapped {count:,} products by style ID")

    cur.close()
    conn.close()

    return count


def map_by_embedding_similarity(min_similarity=0.85):
    """Map alias → stockx by embedding similarity"""
    print(f"\n🎯 Mapping by embedding similarity (min: {min_similarity})...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Get all unmapped alias products
    cur.execute("""
        SELECT product_id_internal, embedding
        FROM products
        WHERE platform = 'alias'
          AND embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM product_mapping pm
              WHERE pm.alias_product_id = products.product_id_internal
          )
    """)

    alias_products = cur.fetchall()
    total = len(alias_products)

    print(f"   Found {total:,} unmapped alias products")

    if total == 0:
        cur.close()
        conn.close()
        return 0

    mapped_count = 0

    for i, (alias_id, alias_embedding) in enumerate(alias_products, 1):
        # Find most similar stockx product
        cur.execute("""
            SELECT
                product_id_internal,
                1 - (embedding <=> %s::vector) AS similarity
            FROM products
            WHERE platform = 'stockx'
              AND embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT 1
        """, (alias_embedding,))

        result = cur.fetchone()

        if result and result[1] >= min_similarity:
            stockx_id, similarity = result

            # Insert mapping
            cur.execute("""
                INSERT INTO product_mapping (
                    alias_product_id,
                    stockx_product_id,
                    confidence_score,
                    mapping_method,
                    created_by
                ) VALUES (%s, %s, %s, 'embedding_similarity', 'system')
                ON CONFLICT (alias_product_id) DO NOTHING
            """, (alias_id, stockx_id, round(similarity, 2)))

            mapped_count += 1

        if i % 100 == 0:
            conn.commit()
            print(f"   Progress: {i:,}/{total:,} ({i/total*100:.1f}%) | Mapped: {mapped_count:,}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"   ✅ Mapped {mapped_count:,} products by embedding similarity")

    return mapped_count


def show_stats():
    """Show mapping statistics"""
    print("\n📊 Mapping Statistics:")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Total mappings
    cur.execute("SELECT COUNT(*) FROM product_mapping")
    total_mappings = cur.fetchone()[0]

    # By method
    cur.execute("""
        SELECT mapping_method, COUNT(*), AVG(confidence_score)
        FROM product_mapping
        GROUP BY mapping_method
        ORDER BY COUNT(*) DESC
    """)

    print(f"\n   Total mappings: {total_mappings:,}")
    print("\n   By method:")
    for method, count, avg_confidence in cur.fetchall():
        print(f"      {method:25s}: {count:6,} (avg confidence: {avg_confidence:.2f})")

    # Unmapped alias products
    cur.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE platform = 'alias'
          AND NOT EXISTS (
              SELECT 1 FROM product_mapping pm
              WHERE pm.alias_product_id = products.product_id_internal
          )
    """)

    unmapped = cur.fetchone()[0]
    print(f"\n   Unmapped alias products: {unmapped:,}")

    cur.close()
    conn.close()


def set_default_aliases():
    """Set default alias for each StockX product (highest confidence match)"""
    print("\n🎯 Setting default aliases for price search...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # For each stockx product with mappings, pick the best alias as default
    cur.execute("""
        WITH ranked_aliases AS (
            SELECT
                mapping_id,
                stockx_product_id,
                ROW_NUMBER() OVER (
                    PARTITION BY stockx_product_id
                    ORDER BY confidence_score DESC, mapping_id ASC
                ) as rank
            FROM product_mapping
        )
        UPDATE product_mapping
        SET is_default_alias = TRUE
        WHERE mapping_id IN (
            SELECT mapping_id FROM ranked_aliases WHERE rank = 1
        )
    """)

    count = cur.rowcount
    conn.commit()

    print(f"   ✅ Set {count:,} default aliases")

    cur.close()
    conn.close()

    return count


def main():
    print("\n" + "="*80)
    print("CREATE PRODUCT MAPPINGS: Alias → StockX")
    print("="*80)

    # Step 1: Create table
    create_table()

    # Step 2: Map by style ID (exact matches)
    style_id_count = map_by_style_id()

    # Step 3: Map by embedding similarity (semantic matches)
    embedding_count = map_by_embedding_similarity(min_similarity=0.85)

    # Step 4: Set default aliases for price search
    default_count = set_default_aliases()

    # Step 5: Show stats
    show_stats()

    print("\n" + "="*80)
    print("✅ MAPPING COMPLETE")
    print("="*80)
    print(f"\nTotal mapped: {style_id_count + embedding_count:,}")
    print(f"Default aliases set: {default_count:,}")
    print("\nYou can now query inventory with canonical StockX product info!")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
