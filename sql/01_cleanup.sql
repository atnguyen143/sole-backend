-- ============================================================
-- SUPABASE CLEANUP SCRIPT
-- ============================================================
-- WARNING: This script will DELETE existing data!
-- Make sure you have a backup before running this.
-- ============================================================

\echo '============================================================'
\echo 'SUPABASE CLEANUP - Phase 1'
\echo '============================================================'
\echo 'WARNING: This will delete existing products data!'
\echo 'Press Ctrl+C now to cancel, or Enter to continue...'
\prompt 'Continue? (yes/no): ' confirm

-- Only proceed if user typed 'yes'
\if :'confirm' = 'yes'

\echo ''
\echo 'Starting cleanup...'
\echo ''

-- ============================================================
-- Step 1: Drop Indexes
-- ============================================================
\echo '📦 Dropping existing indexes...'

-- Drop vector index on old product_embeddings table
DROP INDEX IF EXISTS idx_product_embeddings_cosine;
\echo '   ✓ Dropped idx_product_embeddings_cosine'

-- Drop indexes on old products table
DROP INDEX IF EXISTS idx_products_style_id;
\echo '   ✓ Dropped idx_products_style_id (if existed)'

DROP INDEX IF EXISTS idx_products_name;
\echo '   ✓ Dropped idx_products_name (if existed)'

DROP INDEX IF EXISTS idx_products_brand;
\echo '   ✓ Dropped idx_products_brand (if existed)'

\echo ''

-- ============================================================
-- Step 2: Drop Functions
-- ============================================================
\echo '🔧 Dropping existing functions...'

-- Drop all versions of the function
DROP FUNCTION IF EXISTS find_platform_matched_product_ids(vector(1536), float, int);
DROP FUNCTION IF EXISTS find_platform_matched_product_ids(vector, float, int);
DROP FUNCTION IF EXISTS find_platform_matched_product_ids;
\echo '   ✓ Dropped find_platform_matched_product_ids function'

\echo ''

-- ============================================================
-- Step 3: Drop Tables
-- ============================================================
\echo '🗑️  Dropping existing tables...'

-- Drop product_embeddings table (CASCADE to drop dependent objects)
DROP TABLE IF EXISTS product_embeddings CASCADE;
\echo '   ✓ Dropped product_embeddings table'

-- Drop old products table (CASCADE to drop dependent objects)
DROP TABLE IF EXISTS products CASCADE;
\echo '   ✓ Dropped products table'

\echo ''
\echo '✅ Cleanup complete!'
\echo ''
\echo 'Next step: Run 02_create_schema.sql to create new schema'
\echo ''

\else
\echo ''
\echo '❌ Cleanup cancelled by user'
\echo ''
\endif
