-- ============================================================
-- SUPABASE VERIFICATION SCRIPT
-- ============================================================
-- Runs verification queries to ensure migration was successful
-- ============================================================

\echo '============================================================'
\echo 'SUPABASE VERIFICATION - Phase 4'
\echo '============================================================'
\echo ''

-- ============================================================
-- Step 1: Basic Table Checks
-- ============================================================
\echo '📊 Basic table statistics:'
\echo ''

\echo '1. Total products count:'
SELECT COUNT(*) as total_products FROM products;
\echo ''

\echo '2. Products with embeddings:'
SELECT COUNT(*) as products_with_embeddings FROM products WHERE embedding IS NOT NULL;
\echo ''

\echo '3. Products with embedding_text:'
SELECT COUNT(*) as products_with_embedding_text FROM products WHERE embedding_text IS NOT NULL;
\echo ''

-- ============================================================
-- Step 2: Platform Distribution
-- ============================================================
\echo '📈 Platform distribution:'
\echo ''

SELECT
  COUNT(*) FILTER (WHERE product_id_stockx IS NOT NULL) as stockx_only_count,
  COUNT(*) FILTER (WHERE product_id_alias IS NOT NULL) as alias_only_count,
  COUNT(*) FILTER (WHERE product_id_stockx IS NOT NULL AND product_id_alias IS NOT NULL) as both_platforms_count,
  COUNT(*) as total_count
FROM products;
\echo ''

-- ============================================================
-- Step 3: Data Quality Checks
-- ============================================================
\echo '✅ Data quality checks:'
\echo ''

\echo '1. Products with NULL names (should be 0):'
SELECT COUNT(*) as null_names FROM products WHERE product_name IS NULL OR product_name = '';
\echo ''

\echo '2. Products with style_id_normalized:'
SELECT COUNT(*) as normalized_style_ids FROM products WHERE style_id_normalized IS NOT NULL;
\echo ''

\echo '3. Sample of normalized style IDs:'
SELECT DISTINCT
  style_id as original,
  style_id_normalized as normalized
FROM products
WHERE style_id IS NOT NULL
LIMIT 10;
\echo ''

-- ============================================================
-- Step 4: Index Verification
-- ============================================================
\echo '🔍 Index verification:'
\echo ''

SELECT
  schemaname,
  tablename,
  indexname,
  pg_size_pretty(pg_relation_size(indexname::regclass)) as index_size
FROM pg_indexes
WHERE tablename = 'products'
ORDER BY indexname;
\echo ''

-- ============================================================
-- Step 5: Vector Index Check
-- ============================================================
\echo '🤖 Vector index status:'
\echo ''

SELECT
  schemaname,
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE tablename = 'products'
  AND indexname = 'idx_products_embedding_cosine';
\echo ''

-- ============================================================
-- Step 6: Function Test
-- ============================================================
\echo '⚙️  Testing find_platform_matched_product_ids function:'
\echo ''
\echo 'Note: This will only work if there is at least 1 product with an embedding'
\echo ''

-- Test with a random embedding from the table
DO $$
DECLARE
  test_embedding vector(1536);
BEGIN
  -- Get a random embedding
  SELECT embedding INTO test_embedding
  FROM products
  WHERE embedding IS NOT NULL
  LIMIT 1;

  IF test_embedding IS NOT NULL THEN
    RAISE NOTICE 'Testing function with a sample embedding...';
  ELSE
    RAISE NOTICE 'No embeddings found to test with. Run migrate_products.py first.';
  END IF;
END $$;

-- Run test query if embeddings exist
SELECT
  product_name,
  product_style_id,
  platform_name,
  product_id_stockx,
  product_id_alias,
  ROUND(similarity::numeric, 4) as similarity
FROM find_platform_matched_product_ids(
  (SELECT embedding FROM products WHERE embedding IS NOT NULL LIMIT 1),
  0.7,
  5
);
\echo ''

-- ============================================================
-- Step 7: Sample Data
-- ============================================================
\echo '📋 Sample products (first 5):'
\echo ''

SELECT
  product_name,
  style_id,
  brand,
  CASE
    WHEN product_id_stockx IS NOT NULL THEN 'StockX'
    WHEN product_id_alias IS NOT NULL THEN 'Alias'
    ELSE 'Unknown'
  END as platform,
  CASE
    WHEN embedding IS NOT NULL THEN '✓'
    ELSE '✗'
  END as has_embedding
FROM products
LIMIT 5;
\echo ''

-- ============================================================
-- Step 8: Performance Check
-- ============================================================
\echo '⚡ Performance check (vector search timing):'
\echo ''

\timing on
SELECT
  product_name,
  similarity
FROM find_platform_matched_product_ids(
  (SELECT embedding FROM products WHERE embedding IS NOT NULL LIMIT 1),
  0.5,
  10
);
\timing off
\echo ''

-- ============================================================
-- Summary
-- ============================================================
\echo '============================================================'
\echo '✅ VERIFICATION COMPLETE'
\echo '============================================================'
\echo ''
\echo 'Check the results above for:'
\echo '  1. Total product count matches expected'
\echo '  2. All products have embeddings'
\echo '  3. No NULL product names'
\echo '  4. All indexes created successfully'
\echo '  5. Vector search function works'
\echo '  6. Performance is acceptable (< 100ms for 10 results)'
\echo ''
\echo 'If everything looks good, proceed to Phase 5:'
\echo '  - Update application code with new column names'
\echo '  - Test MCP server integration'
\echo ''
