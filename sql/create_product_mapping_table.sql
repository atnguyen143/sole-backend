-- Product Mapping Table
-- Links alias products to their canonical StockX product
-- Relationship: Many alias → One StockX

CREATE TABLE IF NOT EXISTS product_mapping (
    -- Primary key
    mapping_id SERIAL PRIMARY KEY,

    -- Foreign keys to products table
    alias_product_id INTEGER NOT NULL REFERENCES products(product_id_internal),
    stockx_product_id INTEGER NOT NULL REFERENCES products(product_id_internal),

    -- Metadata
    confidence_score DECIMAL(3, 2), -- 0.00 to 1.00 (e.g., 0.95 = 95% match confidence)
    mapping_method VARCHAR(50),     -- 'manual', 'style_id_match', 'embedding_similarity', 'name_match'
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),        -- 'system', 'user_id', 'claude'

    -- Constraints
    UNIQUE(alias_product_id)        -- Each alias can only map to ONE stockx product
);

-- Triggers to enforce platform checks (can't use subqueries in CHECK constraints)
CREATE OR REPLACE FUNCTION validate_product_mapping()
RETURNS TRIGGER AS $$
BEGIN
    -- Check alias_product is from alias platform
    IF (SELECT platform FROM products WHERE product_id_internal = NEW.alias_product_id) != 'alias' THEN
        RAISE EXCEPTION 'alias_product_id must reference an alias product';
    END IF;

    -- Check stockx_product is from stockx platform
    IF (SELECT platform FROM products WHERE product_id_internal = NEW.stockx_product_id) != 'stockx' THEN
        RAISE EXCEPTION 'stockx_product_id must reference a stockx product';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_product_mapping_trigger
BEFORE INSERT OR UPDATE ON product_mapping
FOR EACH ROW EXECUTE FUNCTION validate_product_mapping();

-- Indexes for fast lookups
CREATE INDEX idx_product_mapping_alias ON product_mapping(alias_product_id);
CREATE INDEX idx_product_mapping_stockx ON product_mapping(stockx_product_id);
CREATE INDEX idx_product_mapping_method ON product_mapping(mapping_method);

-- Usage examples:

-- Find StockX product for a given alias product
-- SELECT pm.*, sp.*
-- FROM product_mapping pm
-- JOIN products sp ON pm.stockx_product_id = sp.product_id_internal
-- WHERE pm.alias_product_id = 123;

-- Find all alias products that map to a StockX product
-- SELECT pm.*, ap.*
-- FROM product_mapping pm
-- JOIN products ap ON pm.alias_product_id = ap.product_id_internal
-- WHERE pm.stockx_product_id = 456;

-- Get inventory with canonical StockX product info
-- SELECT
--     i.*,
--     ap.product_name_platform as alias_name,
--     sp.product_name_platform as stockx_name,
--     sp.style_id_platform as stockx_style_id
-- FROM inventory i
-- LEFT JOIN products ap ON i.product_id_internal = ap.product_id_internal
-- LEFT JOIN product_mapping pm ON ap.product_id_internal = pm.alias_product_id
-- LEFT JOIN products sp ON pm.stockx_product_id = sp.product_id_internal
-- WHERE i.alias_catalog_id IS NOT NULL;
