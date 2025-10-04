-- Add normalized search column to products table
-- This allows matching against unstructured queries (auto-uppercased)

-- Add normalized column (generated from product_name_platform)
ALTER TABLE products
ADD COLUMN IF NOT EXISTS product_name_normalized TEXT
GENERATED ALWAYS AS (UPPER(TRIM(product_name_platform))) STORED;

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_products_name_normalized
ON products(product_name_normalized);

-- Now you can query like:
-- SELECT * FROM products WHERE product_name_normalized = UPPER('bred 11 low');
