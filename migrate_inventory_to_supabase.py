"""
Migrate Inventory from MySQL to Supabase
=========================================

This script:
1. Reads all inventory from MySQL (se_assistant.inventory)
2. Converts camelCase → snake_case
3. Auto-links to products table via product_id_internal
4. Inserts into Supabase inventory table

Run AFTER:
- Creating inventory table in Supabase (sql/inventory_supabase_schema.sql)
- Migrating products to Supabase (migrate_products_full.py)
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

# Column mapping: MySQL camelCase → Supabase snake_case
COLUMN_MAPPING = {
    'sku': 'sku',
    'sold': 'sold',
    'datePurchase': 'date_purchase',
    'placeOfPurchase': 'place_of_purchase',
    'item': 'item',
    'size': 'size',
    'costPrice': 'cost_price',
    'salesTax': 'sales_tax',
    'additionalCost': 'additional_cost',
    'rebate': 'rebate',
    'totalCost': 'total_cost',
    'reshippingCost': 'reshipping_cost',
    'reshippingDuties': 'reshipping_duties',
    'reshippingReferenceNumber': 'reshipping_reference_number',
    'paymentMethod': 'payment_method',
    'salesTaxRefunded': 'sales_tax_refunded',
    'salesTaxRefundDepositDate': 'sales_tax_refund_deposit_date',
    'salesTaxRefundDepositAccount': 'sales_tax_refund_deposit_account',
    'salesTaxRefundReferenceNumber': 'sales_tax_refund_reference_number',
    'salesTaxRefundTotalAmount': 'sales_tax_refund_total_amount',
    'refundDate': 'refund_date',
    'location': 'location',
    'plannedSalesMethod': 'planned_sales_method',
    'referenceNumber': 'reference_number',
    'deliveryDate': 'delivery_date',
    'verificationDate': 'verification_date',
    'createdAt': 'created_at',
    'stockx_productId': 'stockx_product_id',
    'stockx_variantId': 'stockx_variant_id',
    'alias_catalog_id': 'alias_catalog_id',
    'styleId': 'style_id',
    'poolId': 'pool_id',
    'poolKey': 'pool_key',
    'comment': 'comment',
    'updatedVia': 'updated_via',
    'saleTrackerRowIndex': 'sale_tracker_row_index',
}


def build_product_lookup():
    """Build lookup dictionaries from Supabase products table"""
    print("\n📊 Building product lookup from Supabase...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # StockX: UUID → product_id_internal
    cur.execute("""
        SELECT product_id_platform, product_id_internal
        FROM products
        WHERE platform = 'stockx'
    """)
    stockx_lookup = {row[0]: row[1] for row in cur.fetchall()}
    print(f"   ✅ Loaded {len(stockx_lookup):,} StockX products")

    # Alias: catalogId → product_id_internal
    cur.execute("""
        SELECT product_id_platform, product_id_internal
        FROM products
        WHERE platform = 'alias'
    """)
    alias_lookup = {row[0]: row[1] for row in cur.fetchall()}
    print(f"   ✅ Loaded {len(alias_lookup):,} Alias products\n")

    cur.close()
    conn.close()

    return stockx_lookup, alias_lookup


def fetch_inventory_from_mysql():
    """Fetch all inventory from MySQL"""
    print("📦 Fetching inventory from MySQL...")

    conn = pymysql.connect(**MYSQL_CONFIG)
    cur = conn.cursor(pymysql.cursors.DictCursor)

    cur.execute("SELECT * FROM inventory")
    inventory_items = cur.fetchall()

    print(f"   ✅ Fetched {len(inventory_items):,} inventory items\n")

    cur.close()
    conn.close()

    return inventory_items


def transform_inventory_item(item, stockx_lookup, alias_lookup):
    """
    Transform MySQL inventory item to Supabase format
    - Converts camelCase → snake_case
    - Links to product_id_internal
    """
    transformed = {}

    # Map columns
    for mysql_col, supa_col in COLUMN_MAPPING.items():
        value = item.get(mysql_col)

        # Convert tinyint to boolean
        if supa_col in ['sold', 'sales_tax_refunded'] and value is not None:
            value = bool(value)

        transformed[supa_col] = value

    # Link to products table via product_id_internal
    stockx_id = item.get('stockx_productId')
    alias_id = item.get('alias_catalog_id')

    product_id_internal = None

    if stockx_id and stockx_id in stockx_lookup:
        product_id_internal = stockx_lookup[stockx_id]
    elif alias_id and alias_id in alias_lookup:
        product_id_internal = alias_lookup[alias_id]

    transformed['product_id_internal'] = product_id_internal

    # New columns (not in MySQL)
    transformed['inbound_route'] = None
    transformed['reference_number_master'] = None

    return transformed


def insert_to_supabase(inventory_items):
    """Insert transformed inventory into Supabase"""
    print(f"💾 Inserting {len(inventory_items):,} items into Supabase...\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    stats = {
        'inserted': 0,
        'failed': 0,
        'linked_stockx': 0,
        'linked_alias': 0,
        'unlinked': 0
    }

    # Build column list dynamically
    columns = list(COLUMN_MAPPING.values()) + ['product_id_internal', 'inbound_route', 'reference_number_master']
    placeholders = ', '.join(['%s'] * len(columns))
    column_str = ', '.join(columns)

    insert_sql = f"""
        INSERT INTO inventory ({column_str})
        VALUES ({placeholders})
        ON CONFLICT (sku) DO UPDATE SET
            sold = EXCLUDED.sold,
            location = EXCLUDED.location,
            product_id_internal = EXCLUDED.product_id_internal
    """

    for i, item in enumerate(inventory_items, 1):
        try:
            # Build values tuple in same order as columns
            values = tuple(item.get(col) for col in columns)

            cur.execute(insert_sql, values)
            stats['inserted'] += 1

            # Track linking stats
            if item['product_id_internal']:
                if item['stockx_product_id']:
                    stats['linked_stockx'] += 1
                else:
                    stats['linked_alias'] += 1
            else:
                stats['unlinked'] += 1

            if i % 100 == 0:
                conn.commit()
                print(f"   💾 Progress: {i:,}/{len(inventory_items):,} ({i/len(inventory_items)*100:.1f}%)")

        except Exception as e:
            stats['failed'] += 1
            print(f"   ❌ Failed to insert {item['sku']}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    return stats


def main():
    print("\n" + "="*80)
    print("INVENTORY MIGRATION: MySQL → Supabase")
    print("="*80)

    # Step 1: Build product lookup
    stockx_lookup, alias_lookup = build_product_lookup()

    # Step 2: Fetch inventory from MySQL
    mysql_inventory = fetch_inventory_from_mysql()

    # Step 3: Transform items
    print("🔄 Transforming inventory items (camelCase → snake_case)...")
    transformed_items = []
    for item in mysql_inventory:
        transformed = transform_inventory_item(item, stockx_lookup, alias_lookup)
        transformed_items.append(transformed)
    print(f"   ✅ Transformed {len(transformed_items):,} items\n")

    # Step 4: Insert to Supabase
    stats = insert_to_supabase(transformed_items)

    # Step 5: Show results
    print("\n" + "="*80)
    print("MIGRATION RESULTS")
    print("="*80)
    print(f"✅ Inserted:           {stats['inserted']:,}")
    print(f"❌ Failed:             {stats['failed']:,}")
    print(f"\n📊 Product Linking:")
    print(f"   Linked via StockX:  {stats['linked_stockx']:,}")
    print(f"   Linked via Alias:   {stats['linked_alias']:,}")
    print(f"   Unlinked:           {stats['unlinked']:,}")
    print(f"\n📈 Link Rate: {(stats['linked_stockx'] + stats['linked_alias'])/stats['inserted']*100:.1f}%")

    # Step 6: Verification
    print("\n" + "="*80)
    print("VERIFICATION")
    print("="*80)

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM inventory")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inventory WHERE product_id_internal IS NOT NULL")
    linked = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM inventory WHERE sold = FALSE")
    unsold = cur.fetchone()[0]

    print(f"Total inventory:        {total:,}")
    print(f"Linked to products:     {linked:,} ({linked/total*100:.1f}%)")
    print(f"Unsold inventory:       {unsold:,}")

    # Sample items
    cur.execute("""
        SELECT i.sku, i.item, i.size, p.platform, p.product_name_platform
        FROM inventory i
        LEFT JOIN products p ON i.product_id_internal = p.product_id_internal
        LIMIT 5
    """)

    print(f"\n📦 Sample inventory with product links:")
    for row in cur.fetchall():
        platform = row[3] or 'UNLINKED'
        product_name = row[4] or 'N/A'
        print(f"   [{platform:8}] {row[1]} (Size {row[2]})")
        print(f"               → {product_name}")

    cur.close()
    conn.close()

    print("\n✅ Migration complete!\n")
    print("Next steps:")
    print("1. Verify data in Supabase")
    print("2. Run: RENAME TABLE inventory TO inventory_old; (in MySQL)")
    print("3. Update bot code to use Supabase inventory table")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
