"""
Link Inventory to Supabase Products
====================================

This script populates the product_id_internal column in the inventory table
by matching legacy stockx_productId and alias_catalog_id to the unified
products table in Supabase.

Run this AFTER:
1. Running inventory_redesign.sql
2. Completing product migration to Supabase
"""

import os
import pymysql
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Configuration
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
}

SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}

def link_inventory_products():
    """Link inventory items to Supabase products via product_id_internal"""

    print("\n" + "="*80)
    print("LINKING INVENTORY TO SUPABASE PRODUCTS")
    print("="*80 + "\n")

    # Connect to both databases
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    supa_conn = psycopg2.connect(**SUPABASE_CONFIG)

    mysql_cur = mysql_conn.cursor(pymysql.cursors.DictCursor)
    supa_cur = supa_conn.cursor()

    # Step 1: Create lookup dictionaries from Supabase
    print("📊 Building product lookup tables from Supabase...")

    # StockX products: product_id_platform (UUID) -> product_id_internal
    supa_cur.execute("""
        SELECT product_id_platform, product_id_internal
        FROM products
        WHERE platform = 'stockx'
    """)
    stockx_lookup = {row[0]: row[1] for row in supa_cur.fetchall()}
    print(f"   ✅ Loaded {len(stockx_lookup):,} StockX products")

    # Alias products: product_id_platform (catalogId) -> product_id_internal
    supa_cur.execute("""
        SELECT product_id_platform, product_id_internal
        FROM products
        WHERE platform = 'alias'
    """)
    alias_lookup = {row[0]: row[1] for row in supa_cur.fetchall()}
    print(f"   ✅ Loaded {len(alias_lookup):,} Alias products\n")

    # Step 2: Get inventory items that need linking
    mysql_cur.execute("""
        SELECT sku, stockx_productId, alias_catalog_id
        FROM inventory
        WHERE product_id_internal IS NULL
    """)
    inventory_items = mysql_cur.fetchall()
    print(f"📦 Found {len(inventory_items):,} inventory items to link\n")

    # Step 3: Link inventory to products
    stats = {
        'stockx_linked': 0,
        'alias_linked': 0,
        'not_found': 0,
        'no_platform_id': 0
    }

    updates = []

    for item in inventory_items:
        sku = item['sku']
        stockx_id = item['stockx_productId']
        alias_id = item['alias_catalog_id']

        product_id_internal = None

        # Try StockX first
        if stockx_id and stockx_id in stockx_lookup:
            product_id_internal = stockx_lookup[stockx_id]
            stats['stockx_linked'] += 1
        # Try Alias if no StockX match
        elif alias_id and alias_id in alias_lookup:
            product_id_internal = alias_lookup[alias_id]
            stats['alias_linked'] += 1
        # No match found
        elif stockx_id or alias_id:
            stats['not_found'] += 1
        else:
            stats['no_platform_id'] += 1

        if product_id_internal:
            updates.append((product_id_internal, sku))

    # Step 4: Batch update inventory table
    if updates:
        print(f"💾 Updating {len(updates):,} inventory items...")
        mysql_cur.executemany("""
            UPDATE inventory
            SET product_id_internal = %s
            WHERE sku = %s
        """, updates)
        mysql_conn.commit()
        print(f"   ✅ Updated successfully\n")

    # Step 5: Show results
    print("="*80)
    print("RESULTS")
    print("="*80)
    print(f"✅ Linked via StockX:        {stats['stockx_linked']:,}")
    print(f"✅ Linked via Alias:         {stats['alias_linked']:,}")
    print(f"⚠️  Not found in products:   {stats['not_found']:,}")
    print(f"⚠️  No platform ID:          {stats['no_platform_id']:,}")
    print(f"\n📊 Total linked:             {stats['stockx_linked'] + stats['alias_linked']:,}")

    # Step 6: Verification query
    mysql_cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN product_id_internal IS NOT NULL THEN 1 ELSE 0 END) as linked,
            SUM(CASE WHEN product_id_internal IS NULL THEN 1 ELSE 0 END) as unlinked
        FROM inventory
    """)
    result = mysql_cur.fetchone()
    print(f"\n📋 Final Inventory Status:")
    print(f"   Total items:    {result['total']:,}")
    print(f"   Linked:         {result['linked']:,} ({result['linked']/result['total']*100:.1f}%)")
    print(f"   Unlinked:       {result['unlinked']:,} ({result['unlinked']/result['total']*100:.1f}%)")

    # Step 7: Show sample linked items
    mysql_cur.execute("""
        SELECT sku, item, size, stockx_productId, alias_catalog_id, product_id_internal
        FROM inventory
        WHERE product_id_internal IS NOT NULL
        LIMIT 5
    """)
    print(f"\n📦 Sample linked inventory items:")
    for row in mysql_cur.fetchall():
        platform = "StockX" if row['stockx_productId'] else "Alias"
        print(f"   [{platform}] {row['item']} (Size {row['size']}) -> product_id_internal: {row['product_id_internal']}")

    mysql_cur.close()
    supa_cur.close()
    mysql_conn.close()
    supa_conn.close()

    print("\n✅ Linking complete!\n")


if __name__ == "__main__":
    try:
        link_inventory_products()
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
