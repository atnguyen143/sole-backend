-- Create normalization function for product name matching
-- Handles: uppercase, trim, removes brackets/style IDs

CREATE OR REPLACE FUNCTION normalize_product_name(name TEXT)
RETURNS TEXT AS $$
BEGIN
    IF name IS NULL THEN
        RETURN NULL;
    END IF;

    -- Remove brackets and content (e.g., [IF1858])
    name := REGEXP_REPLACE(name, '\s*\[.*?\]\s*', '', 'g');

    -- Uppercase and trim
    name := UPPER(TRIM(name));

    -- Remove non-letter/space characters (keeps A-Z and spaces only)
    name := REGEXP_REPLACE(name, '[^A-Z ]', '', 'g');

    -- Normalize multiple spaces to single space
    name := REGEXP_REPLACE(name, '\s+', ' ', 'g');

    -- Final trim
    name := TRIM(name);

    RETURN name;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Usage:
-- SELECT * FROM products
-- WHERE normalize_product_name(product_name_platform) = normalize_product_name('Bred 11 Low [DV0833]');

-- Or for inventory matching:
-- SELECT * FROM products
-- WHERE normalize_product_name(product_name_platform) = normalize_product_name('adidas yeezy boost 350 v2');
