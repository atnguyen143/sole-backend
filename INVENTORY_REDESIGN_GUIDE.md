# Inventory Table Redesign Guide

## Overview

This redesign deprecates the old `inventory` table and creates a new unified schema that links to the Supabase `products` table while maintaining backward compatibility.

## What Changed

### New Columns Added
1. **`inbound_route`** - Track shipping/delivery route for receiving inventory
2. **`reference_number_master`** - Group related inventory items together
3. **`product_id_internal`** - Links to unified Supabase `products.product_id_internal`

### Architecture
```
MySQL inventory table
    ├── product_id_internal (NEW) ──┐
    ├── stockx_productId (legacy)   │
    └── alias_catalog_id (legacy)   │
                                    │
                                    ▼
                        Supabase products table
                            ├── product_id_internal (PK)
                            ├── product_id_platform (StockX UUID or Alias catalogId)
                            └── platform ('stockx' or 'alias')
```

## Migration Steps

### Step 1: Backup Current Data
```bash
# Export current inventory table
mysqldump -h 76.191.100.66 -u se_assistant_bot_sole -p se_assistant inventory > inventory_backup.sql
```

### Step 2: Run SQL Migration
```bash
# Connect to MySQL
mysql -h 76.191.100.66 -u se_assistant_bot_sole -p se_assistant

# Run the redesign script
source sql/inventory_redesign.sql
```

This will:
- Rename `inventory` → `inventory_old`
- Create new `inventory` table with enhanced schema
- Migrate all data from old to new table
- Create helper views for querying

### Step 3: Link Inventory to Supabase Products
```bash
# Run after products are migrated to Supabase
python link_inventory_to_products.py
```

This will populate `product_id_internal` by matching:
- `stockx_productId` → Supabase `products` where `platform='stockx'`
- `alias_catalog_id` → Supabase `products` where `platform='alias'`

## Querying the New Schema

### Get inventory with both StockX and Alias product IDs
```sql
-- Using the view (easiest)
SELECT
    sku,
    item,
    size,
    stockx_product_id_platform,
    alias_product_id_platform
FROM inventory_with_platform_ids
WHERE sku = 'SE000001';
```

### Get inventory with unified product reference
```sql
SELECT
    i.sku,
    i.item,
    i.size,
    i.product_id_internal,
    p.product_name_platform,
    p.platform
FROM inventory i
LEFT JOIN products p ON i.product_id_internal = p.product_id_internal
WHERE i.sku = 'SE000001';
```

### Legacy compatibility query
```sql
-- Old way still works
SELECT sku, item, stockx_productId, alias_catalog_id
FROM inventory
WHERE stockx_productId = 'a7cccc96-7da8-4e0d-9df0-3671622f8c0d';
```

## Benefits

### 1. Unified Product Reference
- Single `product_id_internal` links to both StockX and Alias products
- No more maintaining separate `stockx_productId` and `alias_catalog_id`
- Easier to switch platforms or add new platforms

### 2. Better Inventory Grouping
- `reference_number_master` groups related inventory (e.g., bulk purchases)
- `inbound_route` tracks shipping routes for analytics

### 3. Backward Compatible
- All legacy columns preserved
- Views maintain old query patterns
- Gradual migration path

### 4. Supports Multiple Platforms
```sql
-- Example: Same inventory item might exist on both platforms
SELECT
    i.sku,
    i.item,
    stockx.product_id_platform AS stockx_id,
    alias.product_id_platform AS alias_id
FROM inventory i
LEFT JOIN products stockx ON i.product_id_internal = stockx.product_id_internal AND stockx.platform = 'stockx'
LEFT JOIN products alias ON i.product_id_internal = alias.product_id_internal AND alias.platform = 'alias';
```

## Example Usage

### Adding new inventory item
```sql
INSERT INTO inventory (
    sku,
    item,
    size,
    datePurchase,
    placeOfPurchase,
    inbound_route,
    reference_number_master,
    totalCost,
    product_id_internal
) VALUES (
    'SE999999',
    'Jordan 1 Retro High OG Black Toe',
    '10',
    '2025-10-03',
    'Nike SNKRS',
    'UPS Ground',
    'SNKRS-20251003',
    180.00,
    12345  -- From Supabase products table
);
```

### Querying with platform details
```python
# Python example
import pymysql
import psycopg2

# Get inventory from MySQL
mysql_cur.execute("SELECT * FROM inventory WHERE sku = %s", ('SE999999',))
inv = mysql_cur.fetchone()

# Get product details from Supabase
supa_cur.execute("""
    SELECT platform, product_name_platform, style_id_platform
    FROM products
    WHERE product_id_internal = %s
""", (inv['product_id_internal'],))
product = supa_cur.fetchone()

print(f"{inv['item']} is on {product['platform']} as {product['product_name_platform']}")
```

## Rollback Plan

If you need to rollback:

```sql
-- Drop new table and views
DROP VIEW IF EXISTS inventory_with_platform_ids;
DROP VIEW IF EXISTS inventory_legacy_mapping;
DROP TABLE IF EXISTS inventory;

-- Restore old table
RENAME TABLE inventory_old TO inventory;
```

## Next Steps

1. ✅ Run `sql/inventory_redesign.sql` to create new schema
2. ✅ Verify data migrated correctly
3. ✅ Run `link_inventory_to_products.py` to populate product_id_internal
4. 🔄 Update bot code to use new schema
5. 🔄 Monitor for issues
6. 🗑️ Drop `inventory_old` after 30 days if no issues

## Files

- [`sql/inventory_redesign.sql`](sql/inventory_redesign.sql) - SQL migration script
- [`link_inventory_to_products.py`](link_inventory_to_products.py) - Python linking script
- This guide - Reference documentation
