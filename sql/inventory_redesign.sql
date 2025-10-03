-- ============================================================================
-- INVENTORY TABLE REDESIGN
-- ============================================================================
--
-- This migration:
-- 1. Renames current inventory table to inventory_old
-- 2. Creates new inventory table with unified product references
-- 3. Creates view to show StockX and Alias product IDs
-- 4. Maintains backward compatibility
--
-- Run this in MySQL (se_assistant database)
-- ============================================================================

-- Step 1: Rename existing inventory table
RENAME TABLE inventory TO inventory_old;

-- Step 2: Create new inventory table with enhanced schema
CREATE TABLE inventory (
    -- Primary Key
    sku VARCHAR(100) PRIMARY KEY,

    -- Core Inventory Info
    sold TINYINT(1) NOT NULL DEFAULT 0,
    datePurchase DATE,
    placeOfPurchase VARCHAR(255),
    inbound_route VARCHAR(255) COMMENT 'Shipping/delivery route for inbound inventory',
    item VARCHAR(512),
    size VARCHAR(50),

    -- Pricing
    costPrice DECIMAL(10,2),
    salesTax DECIMAL(10,2),
    additionalCost DECIMAL(10,2),
    rebate DECIMAL(10,2),
    totalCost DECIMAL(10,2),

    -- Reshipping Costs
    reshippingCost DECIMAL(10,2),
    reshippingDuties DECIMAL(10,2),
    reshippingReferenceNumber VARCHAR(255),

    -- Payment & Refund
    paymentMethod VARCHAR(100),
    salesTaxRefunded TINYINT(1),
    salesTaxRefundDepositDate DATE,
    salesTaxRefundDepositAccount VARCHAR(255),
    salesTaxRefundReferenceNumber VARCHAR(255),
    salesTaxRefundTotalAmount DECIMAL(10,2),
    refundDate DATE,

    -- Location & Status
    location VARCHAR(255),
    plannedSalesMethod VARCHAR(100),

    -- Reference Numbers
    referenceNumber VARCHAR(255) COMMENT 'Original reference number (order/tracking)',
    reference_number_master VARCHAR(255) COMMENT 'Master reference for grouping related inventory',

    -- Dates
    deliveryDate DATE,
    verificationDate DATE,
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Product Linking (NEW - Links to Supabase unified products table)
    product_id_internal INT COMMENT 'References products.product_id_internal in Supabase',

    -- Legacy Platform-Specific IDs (kept for backward compatibility)
    stockx_productId VARCHAR(255) COMMENT 'Legacy StockX product UUID',
    stockx_variantId VARCHAR(255) COMMENT 'Legacy StockX variant UUID',
    alias_catalog_id VARCHAR(255) COMMENT 'Legacy Alias catalog ID',
    styleId VARCHAR(255) COMMENT 'Legacy style ID extracted from item name',

    -- Pool Management
    poolId VARCHAR(255),
    poolKey VARCHAR(255),

    -- Metadata
    comment TEXT,
    updatedVia VARCHAR(255),
    saleTrackerRowIndex VARCHAR(255),

    -- Indexes for performance
    INDEX idx_item (item),
    INDEX idx_size (size),
    INDEX idx_location (location),
    INDEX idx_stockx_productId (stockx_productId),
    INDEX idx_stockx_variantId (stockx_variantId),
    INDEX idx_poolKey (poolKey),
    INDEX idx_product_id_internal (product_id_internal),
    INDEX idx_sold (sold),
    INDEX idx_date_purchase (datePurchase)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Redesigned inventory table with unified product references to Supabase';

-- Step 3: Migrate data from old table to new table
INSERT INTO inventory (
    sku, sold, datePurchase, placeOfPurchase, item, size,
    costPrice, salesTax, additionalCost, rebate, totalCost,
    reshippingCost, reshippingDuties, reshippingReferenceNumber,
    paymentMethod, salesTaxRefunded, salesTaxRefundDepositDate,
    salesTaxRefundDepositAccount, salesTaxRefundReferenceNumber,
    salesTaxRefundTotalAmount, refundDate, location, plannedSalesMethod,
    referenceNumber, deliveryDate, verificationDate, createdAt,
    stockx_productId, stockx_variantId, alias_catalog_id, styleId,
    poolId, poolKey, comment, updatedVia, saleTrackerRowIndex
)
SELECT
    sku, sold, datePurchase, placeOfPurchase, item, size,
    costPrice, salesTax, additionalCost, rebate, totalCost,
    reshippingCost, reshippingDuties, reshippingReferenceNumber,
    paymentMethod, salesTaxRefunded, salesTaxRefundDepositDate,
    salesTaxRefundDepositAccount, salesTaxRefundReferenceNumber,
    salesTaxRefundTotalAmount, refundDate, location, plannedSalesMethod,
    referenceNumber, deliveryDate, verificationDate, createdAt,
    stockx_productId, stockx_variantId, alias_catalog_id, styleId,
    poolId, poolKey, comment, updatedVia, saleTrackerRowIndex
FROM inventory_old;

-- Step 4: Create view to display platform-specific product IDs from Supabase
-- This view joins inventory with Supabase products table to show both StockX and Alias IDs
CREATE OR REPLACE VIEW inventory_with_platform_ids AS
SELECT
    i.*,
    -- StockX Product Info (from Supabase)
    p_stockx.product_id_platform AS stockx_product_id_platform,
    p_stockx.product_name_platform AS stockx_product_name,
    p_stockx.style_id_platform AS stockx_style_id,

    -- Alias Product Info (from Supabase)
    p_alias.product_id_platform AS alias_product_id_platform,
    p_alias.product_name_platform AS alias_product_name,
    p_alias.style_id_platform AS alias_style_id

FROM inventory i

-- Left join to get StockX product details
LEFT JOIN (
    -- This would connect to Supabase products table
    -- For now, using legacy stockx_productId
    SELECT product_id_internal, product_id_platform, product_name_platform, style_id_platform
    FROM products  -- This assumes federated query or separate join
    WHERE platform = 'stockx'
) p_stockx ON i.product_id_internal = p_stockx.product_id_internal

-- Left join to get Alias product details
LEFT JOIN (
    SELECT product_id_internal, product_id_platform, product_name_platform, style_id_platform
    FROM products
    WHERE platform = 'alias'
) p_alias ON i.product_id_internal = p_alias.product_id_internal;

-- Step 5: Create helper view for legacy compatibility
-- Maps old stockx_productId/alias_catalog_id to new structure
CREATE OR REPLACE VIEW inventory_legacy_mapping AS
SELECT
    i.sku,
    i.item,
    i.size,
    i.sold,

    -- Show both old and new product references
    i.stockx_productId AS legacy_stockx_uuid,
    i.alias_catalog_id AS legacy_alias_catalog_id,
    i.product_id_internal AS new_product_id_internal,

    -- Direct platform lookups (for queries that need specific platform)
    CASE
        WHEN i.stockx_productId IS NOT NULL THEN i.stockx_productId
        ELSE NULL
    END AS active_stockx_id,

    CASE
        WHEN i.alias_catalog_id IS NOT NULL THEN i.alias_catalog_id
        ELSE NULL
    END AS active_alias_id

FROM inventory i;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================

-- Check row counts match
SELECT 'inventory_old' AS table_name, COUNT(*) AS row_count FROM inventory_old
UNION ALL
SELECT 'inventory' AS table_name, COUNT(*) AS row_count FROM inventory;

-- Show sample from new table with new columns
SELECT
    sku,
    item,
    placeOfPurchase,
    inbound_route,
    reference_number_master,
    product_id_internal,
    stockx_productId,
    alias_catalog_id
FROM inventory
LIMIT 5;

-- Show view output
SELECT * FROM inventory_legacy_mapping LIMIT 5;

-- ============================================================================
-- NOTES
-- ============================================================================
--
-- NEW COLUMNS ADDED:
-- 1. inbound_route - Track shipping/delivery route for receiving inventory
-- 2. reference_number_master - Group related inventory items
-- 3. product_id_internal - Link to unified Supabase products table
--
-- TO LINK INVENTORY TO SUPABASE PRODUCTS:
-- You'll need to run a separate script to populate product_id_internal
-- by matching stockx_productId/alias_catalog_id to Supabase products table
--
-- BACKWARD COMPATIBILITY:
-- - All original columns preserved
-- - Legacy views maintain old query patterns
-- - Old stockx/alias IDs still available for transition period
--
-- ============================================================================
