"""
Migrate Inventory from MySQL to Supabase (v2)
==============================================

This script:
1. Reads all inventory from MySQL
2. Matches by ITEM NAME to Supabase products (NOT legacy IDs)
3. Caches matches to minimize repeated queries
4. Converts camelCase → snake_case
5. Inserts into Supabase inventory table

Strategy:
- Extract unique item names from MySQL inventory
- Query Supabase products for each unique name (semantic search)
- Cache results for reuse
- Link inventory → products via product_id_internal
"""

import os
import re
import pymysql
import psycopg2
from dotenv import load_dotenv
from collections import defaultdict

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


def normalize_item_name(item_name):
    """
    Normalize item name for matching
    Example: "Jordan 1 Retro High Pine Green [555088-302]" → "jordan 1 retro high pine green [555088-302]"
    KEEPS the style ID in brackets for precise matching
    """
    if not item_name:
        return None

    # Lowercase, strip, normalize spaces (KEEP brackets and style ID)
    name = item_name.lower().strip()
    name = re.sub(r'\s+', ' ', name)

    return name


def extract_style_id_from_item(item_name):
    """Extract style ID from brackets if present"""
    if not item_name:
        return None

    match = re.search(r'\[([^\]]+)\]', item_name)
    return match.group(1) if match else None


def build_item_to_product_cache(inventory_items):
    """
    Build cache mapping item names to product_id_internal
    Queries Supabase once per unique item name
    """
    print("\n🔍 Building item → product mapping cache...")

    # Get unique item names
    unique_items = {}
    for item in inventory_items:
        item_name = item.get('item')
        if item_name:
            normalized = normalize_item_name(item_name)
            if normalized and normalized not in unique_items:
                unique_items[normalized] = {
                    'original': item_name,
                    'style_id': extract_style_id_from_item(item_name)
                }

    print(f"   Found {len(unique_items):,} unique item names to match\n")

    # Query Supabase for each unique name
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    cache = {}
    stats = {'exact_match': 0, 'no_match': 0, 'multiple_match': 0}

    for i, (normalized_name, item_info) in enumerate(unique_items.items(), 1):
        # Try exact name match first
        cur.execute("""
            SELECT product_id_internal, product_name_platform, platform, style_id_platform
            FROM products
            WHERE LOWER(product_name_platform) = %s
            LIMIT 5
        """, (normalized_name,))

        matches = cur.fetchall()

        if len(matches) == 1:
            # Single exact match - best case
            stats['exact_match'] += 1
            cache[normalized_name] = {
                'product_id_internal': matches[0][0],
                'matched_name': matches[0][1],
                'platform': matches[0][2],
                'confidence': 'exact'
            }
        elif len(matches) > 1:
            # Multiple matches - prioritize by style ID if available
            stats['multiple_match'] += 1
            extracted_style = item_info['style_id']

            best_match = matches[0]  # Default to first
            if extracted_style:
                for match in matches:
                    if match[3] and extracted_style.lower() in match[3].lower():
                        best_match = match
                        break

            cache[normalized_name] = {
                'product_id_internal': best_match[0],
                'matched_name': best_match[1],
                'platform': best_match[2],
                'confidence': 'multi-match'
            }
        else:
            # No match - try fuzzy match or leave unlinked
            stats['no_match'] += 1
            cache[normalized_name] = None

        if i % 100 == 0:
            print(f"   Progress: {i:,}/{len(unique_items):,} ({i/len(unique_items)*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n📊 Matching Results:")
    print(f"   ✅ Exact matches:      {stats['exact_match']:,}")
    print(f"   ⚠️  Multiple matches:   {stats['multiple_match']:,}")
    print(f"   ❌ No matches:         {stats['no_match']:,}")
    print(f"   Match rate: {(stats['exact_match'] + stats['multiple_match'])/len(unique_items)*100:.1f}%\n")

    return cache


def transform_inventory_item(item, item_cache):
    """Transform MySQL inventory item to Supabase format"""
    transformed = {}

    # Column mapping
    column_map = {
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

    for mysql_col, supa_col in column_map.items():
        value = item.get(mysql_col)
        if supa_col in ['sold', 'sales_tax_refunded'] and value is not None:
            value = bool(value)
        transformed[supa_col] = value

    # Link to products via item name cache
    item_name = item.get('item')
    product_id_internal = None

    if item_name:
        normalized = normalize_item_name(item_name)
        if normalized and normalized in item_cache:
            match_info = item_cache[normalized]
            if match_info:
                product_id_internal = match_info['product_id_internal']

    transformed['product_id_internal'] = product_id_internal
    transformed['inbound_route'] = None
    transformed['reference_number_master'] = None

    return transformed


def insert_to_supabase(inventory_items):
    """Insert transformed inventory into Supabase"""
    print(f"\n💾 Inserting {len(inventory_items):,} items into Supabase...\n")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    stats = {'inserted': 0, 'failed': 0, 'linked': 0, 'unlinked': 0}

    columns = ['sku', 'sold', 'date_purchase', 'place_of_purchase', 'item', 'size',
               'cost_price', 'sales_tax', 'additional_cost', 'rebate', 'total_cost',
               'reshipping_cost', 'reshipping_duties', 'reshipping_reference_number',
               'payment_method', 'sales_tax_refunded', 'sales_tax_refund_deposit_date',
               'sales_tax_refund_deposit_account', 'sales_tax_refund_reference_number',
               'sales_tax_refund_total_amount', 'refund_date', 'location',
               'planned_sales_method', 'reference_number', 'delivery_date',
               'verification_date', 'created_at', 'stockx_product_id',
               'stockx_variant_id', 'alias_catalog_id', 'style_id', 'pool_id',
               'pool_key', 'comment', 'updated_via', 'sale_tracker_row_index',
               'product_id_internal', 'inbound_route', 'reference_number_master']

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
            values = tuple(item.get(col) for col in columns)
            cur.execute(insert_sql, values)
            stats['inserted'] += 1

            if item['product_id_internal']:
                stats['linked'] += 1
            else:
                stats['unlinked'] += 1

            if i % 100 == 0:
                conn.commit()
                print(f"   Progress: {i:,}/{len(inventory_items):,} ({i/len(inventory_items)*100:.1f}%)")

        except Exception as e:
            stats['failed'] += 1
            print(f"   ❌ Failed: {item['sku']} - {e}")

    conn.commit()
    cur.close()
    conn.close()

    return stats


def create_index_on_products():
    """Create indexes on products table for faster lookups"""
    print("\n🔨 Creating indexes on products table...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Check product count to determine optimal index parameters
    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NOT NULL")
    product_count = cur.fetchone()[0]

    # Calculate optimal lists parameter for IVFFlat: sqrt(total_rows)
    import math
    lists = max(50, min(2000, int(math.sqrt(product_count))))

    print(f"   📊 Found {product_count:,} products with embeddings")
    print(f"   🎯 Using lists = {lists} for vector index\n")

    indexes = [
        {
            'name': 'idx_products_name_lower',
            'sql': """
                CREATE INDEX IF NOT EXISTS idx_products_name_lower
                ON products (LOWER(product_name_platform))
            """,
            'description': 'Name lookup index'
        },
        {
            'name': 'idx_products_embedding',
            'sql': f"""
                CREATE INDEX IF NOT EXISTS idx_products_embedding
                ON products
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """,
            'description': 'Vector similarity index'
        }
    ]

    for idx in indexes:
        try:
            print(f"   🔨 Creating {idx['name']}... ({idx['description']})")
            cur.execute(idx['sql'])
            conn.commit()
            print(f"      ✅ Created\n")
        except Exception as e:
            if 'already exists' in str(e).lower():
                print(f"      ⚠️  Already exists, skipping\n")
            elif 'memory' in str(e).lower():
                print(f"      ⚠️  Insufficient memory for vector index")
                print(f"      💡 Run create_indexes.py separately or use Supabase SQL Editor\n")
            else:
                print(f"      ❌ Error: {e}\n")

    cur.close()
    conn.close()


def main():
    print("\n" + "="*80)
    print("INVENTORY MIGRATION: MySQL → Supabase (Name-Based Matching)")
    print("="*80)

    # Step 0: Create index for faster matching
    create_index_on_products()

    # Step 1: Fetch inventory from MySQL
    print("\n📦 Fetching inventory from MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor(pymysql.cursors.DictCursor)
    mysql_cur.execute("SELECT * FROM inventory")
    mysql_inventory = mysql_cur.fetchall()
    print(f"   ✅ Fetched {len(mysql_inventory):,} items")
    mysql_cur.close()
    mysql_conn.close()

    # Step 2: Build item name → product cache
    item_cache = build_item_to_product_cache(mysql_inventory)

    # Step 3: Transform items
    print("🔄 Transforming inventory items...")
    transformed_items = []
    for item in mysql_inventory:
        transformed = transform_inventory_item(item, item_cache)
        transformed_items.append(transformed)
    print(f"   ✅ Transformed {len(transformed_items):,} items")

    # Step 4: Insert to Supabase
    stats = insert_to_supabase(transformed_items)

    # Step 5: Results
    print("\n" + "="*80)
    print("MIGRATION RESULTS")
    print("="*80)
    print(f"✅ Inserted:     {stats['inserted']:,}")
    print(f"❌ Failed:       {stats['failed']:,}")
    print(f"🔗 Linked:       {stats['linked']:,} ({stats['linked']/stats['inserted']*100:.1f}%)")
    print(f"❓ Unlinked:     {stats['unlinked']:,}")

    print("\n✅ Migration complete!\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
