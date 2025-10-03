-- Create vector index for fast similarity search
-- Run this in Supabase SQL Editor after migration completes
--
-- ⚠️ IMPORTANT: You only need to run this ONCE after the initial migration
-- The index automatically updates when new products are added - no need to rerun!
--
-- However, if you add HUNDREDS OF THOUSANDS more products later,
-- you may want to recreate the index with a higher 'lists' value:
-- - Current lists = 1000 (good for ~462K products)
-- - For 1M+ products, consider lists = 1500-2000
-- - Formula: lists ≈ sqrt(total_rows)

-- Create IVFFlat index for cosine similarity search
-- Using lists = 100 for smaller datasets (~4K products)
-- Increase to 500-1000 once you have 100K+ products
CREATE INDEX IF NOT EXISTS products_embedding_idx
ON products
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create additional indexes for common queries
CREATE INDEX IF NOT EXISTS products_platform_idx ON products(platform);
CREATE INDEX IF NOT EXISTS products_style_id_normalized_idx ON products(style_id_normalized);
CREATE INDEX IF NOT EXISTS products_keyword_idx ON products(keyword_used);

-- Verify index creation
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'products'
ORDER BY indexname;
