-- ============================================================================
-- INVENTORY TABLE - SUPABASE (PostgreSQL)
-- ============================================================================
--
-- This creates the inventory table in Supabase with:
-- - Snake_case naming convention (PostgreSQL standard)
-- - Foreign key to products table via product_id_internal
-- - Enhanced columns: inbound_route, reference_number_master
-- - All legacy columns preserved for backward compatibility
--
-- Run this in Supabase SQL Editor
-- ============================================================================

-- Step 1: Create inventory table in Supabase
CREATE TABLE IF NOT EXISTS inventory (
    -- Primary Key
    sku VARCHAR(100) PRIMARY KEY,

    -- Core Inventory Info
    sold BOOLEAN NOT NULL DEFAULT FALSE,
    date_purchase DATE,
    place_of_purchase VARCHAR(255),
    inbound_route VARCHAR(255),  -- NEW: shipping/delivery route
    item VARCHAR(512),
    size VARCHAR(50),

    -- Pricing
    cost_price DECIMAL(10,2),
    sales_tax DECIMAL(10,2),
    additional_cost DECIMAL(10,2),
    rebate DECIMAL(10,2),
    total_cost DECIMAL(10,2),

    -- Reshipping Costs
    reshipping_cost DECIMAL(10,2),
    reshipping_duties DECIMAL(10,2),
    reshipping_reference_number VARCHAR(255),

    -- Payment & Refund
    payment_method VARCHAR(100),
    sales_tax_refunded BOOLEAN,
    sales_tax_refund_deposit_date DATE,
    sales_tax_refund_deposit_account VARCHAR(255),
    sales_tax_refund_reference_number VARCHAR(255),
    sales_tax_refund_total_amount DECIMAL(10,2),
    refund_date DATE,

    -- Location & Status
    location VARCHAR(255),
    planned_sales_method VARCHAR(100),

    -- Reference Numbers
    reference_number VARCHAR(255),  -- Original order/tracking reference
    reference_number_master VARCHAR(255),  -- NEW: Master reference for grouping

    -- Dates
    delivery_date DATE,
    verification_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Product Linking (NEW - Links to unified products table)
    product_id_internal INTEGER REFERENCES products(product_id_internal),

    -- Legacy Platform-Specific IDs (for backward compatibility & migration)
    stockx_product_id VARCHAR(255),  -- Legacy StockX product UUID
    stockx_variant_id VARCHAR(255),  -- Legacy StockX variant UUID
    alias_catalog_id VARCHAR(255),   -- Legacy Alias catalog ID
    style_id VARCHAR(255),           -- Legacy extracted style ID

    -- Pool Management
    pool_id VARCHAR(255),
    pool_key VARCHAR(255),

    -- Metadata
    comment TEXT,
    updated_via VARCHAR(255),
    sale_tracker_row_index VARCHAR(255)
);

-- Step 2: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory(item);
CREATE INDEX IF NOT EXISTS idx_inventory_size ON inventory(size);
CREATE INDEX IF NOT EXISTS idx_inventory_location ON inventory(location);
CREATE INDEX IF NOT EXISTS idx_inventory_product_id_internal ON inventory(product_id_internal);
CREATE INDEX IF NOT EXISTS idx_inventory_stockx_product_id ON inventory(stockx_product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_alias_catalog_id ON inventory(alias_catalog_id);
CREATE INDEX IF NOT EXISTS idx_inventory_sold ON inventory(sold);
CREATE INDEX IF NOT EXISTS idx_inventory_date_purchase ON inventory(date_purchase);
CREATE INDEX IF NOT EXISTS idx_inventory_pool_key ON inventory(pool_key);

-- Step 3: Add comments for documentation
COMMENT ON TABLE inventory IS 'Physical inventory tracking with unified product references';
COMMENT ON COLUMN inventory.sku IS 'Unique inventory identifier (SE######)';
COMMENT ON COLUMN inventory.inbound_route IS 'Shipping route for receiving inventory (e.g., UPS Ground, Nike SNKRS)';
COMMENT ON COLUMN inventory.reference_number_master IS 'Master reference for grouping related inventory items';
COMMENT ON COLUMN inventory.product_id_internal IS 'Foreign key to products table - unified reference to both StockX and Alias products';
COMMENT ON COLUMN inventory.stockx_product_id IS 'Legacy StockX UUID - kept for migration period';
COMMENT ON COLUMN inventory.alias_catalog_id IS 'Legacy Alias catalog ID - kept for migration period';

-- Step 4: Create view to join inventory with product details
CREATE OR REPLACE VIEW inventory_with_products AS
SELECT
    i.*,
    p.platform,
    p.product_id_platform,
    p.product_name_platform,
    p.style_id_platform,
    p.style_id_normalized,
    p.embedding_text
FROM inventory i
LEFT JOIN products p ON i.product_id_internal = p.product_id_internal;

-- Step 5: Create view for platform-specific product IDs
-- Shows both StockX and Alias product info when available
CREATE OR REPLACE VIEW inventory_platform_breakdown AS
SELECT
    i.sku,
    i.item,
    i.size,
    i.sold,
    i.total_cost,
    i.location,
    i.product_id_internal,

    -- StockX details
    p_stockx.product_id_platform AS stockx_product_id_platform,
    p_stockx.product_name_platform AS stockx_product_name,
    p_stockx.style_id_platform AS stockx_style_id,

    -- Alias details
    p_alias.product_id_platform AS alias_product_id_platform,
    p_alias.product_name_platform AS alias_product_name,
    p_alias.style_id_platform AS alias_style_id,

    -- Legacy IDs
    i.stockx_product_id AS legacy_stockx_uuid,
    i.alias_catalog_id AS legacy_alias_catalog_id

FROM inventory i
LEFT JOIN products p_stockx
    ON i.product_id_internal = p_stockx.product_id_internal
    AND p_stockx.platform = 'stockx'
LEFT JOIN products p_alias
    ON i.product_id_internal = p_alias.product_id_internal
    AND p_alias.platform = 'alias';

-- Step 6: Create view for unsold inventory with product details
CREATE OR REPLACE VIEW inventory_unsold AS
SELECT
    i.sku,
    i.item,
    i.size,
    i.location,
    i.total_cost,
    i.date_purchase,
    p.platform,
    p.product_name_platform,
    p.style_id_platform
FROM inventory i
LEFT JOIN products p ON i.product_id_internal = p.product_id_internal
WHERE i.sold = FALSE
ORDER BY i.date_purchase DESC;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check table exists
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'inventory';

-- Check columns
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'inventory'
ORDER BY ordinal_position;

-- Check indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'inventory'
ORDER BY indexname;

-- Check views
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
AND table_name LIKE 'inventory%'
ORDER BY table_name;

-- ============================================================================
-- NOTES
-- ============================================================================
--
-- MIGRATION PROCESS:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Run migrate_inventory_to_supabase.py to copy data from MySQL
-- 3. Script will auto-link product_id_internal during migration
-- 4. Verify data, then rename MySQL inventory → inventory_old
--
-- QUERYING:
-- - Use inventory_with_products for most queries (includes product details)
-- - Use inventory_platform_breakdown to see both StockX and Alias IDs
-- - Use inventory_unsold for active inventory management
--
-- ============================================================================
