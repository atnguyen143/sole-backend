-- ============================================================
-- SUPABASE SCHEMA CREATION SCRIPT
-- ============================================================
-- Platform-agnostic products table with descriptive column names
-- ============================================================

\echo '============================================================'
\echo 'SUPABASE SCHEMA CREATION - Phase 2'
\echo '============================================================'
\echo ''

-- ============================================================
-- Step 1: Enable Extensions
-- ============================================================
\echo '🔧 Enabling required extensions...'
CREATE EXTENSION IF NOT EXISTS vector;
\echo '   ✓ pgvector extension enabled'
\echo ''

-- ============================================================
-- Step 2: Create Products Table
-- ============================================================
\echo '📦 Creating products table (platform-agnostic design)...'

CREATE TABLE products (
  -- Primary Key (Internal Auto-Incrementing)
  product_id_internal SERIAL PRIMARY KEY,

  -- Platform IDs
  product_id_platform VARCHAR(255) NOT NULL UNIQUE,  -- Platform's product ID
  platform VARCHAR(50) NOT NULL,                     -- 'stockx', 'alias', 'poizon'
  platform_id VARCHAR(255),                          -- RESERVED

  -- Core Product Information
  product_name_platform VARCHAR(512) NOT NULL,       -- Platform's product name
  style_id_platform VARCHAR(255),                    -- Platform's style ID (nullable)
  style_id_normalized VARCHAR(255),                  -- Normalized for matching (nullable)

  -- Platform-Specific Data (Flexible)
  platform_data JSONB,                               -- All platform-specific fields (nullable)

  -- Embeddings
  embedding vector(1536),                            -- Nullable
  embedding_text TEXT,                               -- Nullable

  -- Metadata
  keyword_used TEXT,                                 -- Nullable
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- Constraints (minimal)
  CONSTRAINT products_name_check CHECK (product_name_platform IS NOT NULL AND product_name_platform != ''),
  CONSTRAINT products_platform_check CHECK (platform IN ('stockx', 'alias', 'poizon'))
);

\echo '   ✓ Products table created'
\echo '   ✓ Required fields: product_id_platform, platform, product_name_platform'
\echo '   ✓ All other fields nullable'
\echo ''

-- ============================================================
-- Step 3: Create Standard Indexes
-- ============================================================
\echo '🔍 Creating standard indexes...'

CREATE INDEX idx_products_platform ON products(platform);
\echo '   ✓ Created idx_products_platform'

CREATE INDEX idx_products_product_id_platform ON products(product_id_platform);
\echo '   ✓ Created idx_products_product_id_platform'

CREATE INDEX idx_products_style_id_platform ON products(style_id_platform);
\echo '   ✓ Created idx_products_style_id_platform'

CREATE INDEX idx_products_style_id_normalized ON products(style_id_normalized);
\echo '   ✓ Created idx_products_style_id_normalized'

CREATE INDEX idx_products_name_platform ON products(product_name_platform);
\echo '   ✓ Created idx_products_name_platform'

CREATE INDEX idx_products_platform_composite ON products(platform, product_id_platform);
\echo '   ✓ Created idx_products_platform_composite'

\echo ''

-- ============================================================
-- Step 4: Create JSONB Index
-- ============================================================
\echo '📋 Creating JSONB GIN index for platform_data...'

CREATE INDEX idx_products_platform_data ON products USING GIN (platform_data);
\echo '   ✓ Created idx_products_platform_data'
\echo ''

-- ============================================================
-- Step 5: Create Vector Index
-- ============================================================
\echo '🤖 Creating vector index...'
\echo '   (This may take a few minutes for large datasets)'

SET maintenance_work_mem = '128MB';
CREATE INDEX idx_products_embedding_cosine
  ON products
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
RESET maintenance_work_mem;

\echo '   ✓ Created idx_products_embedding_cosine'
\echo ''

-- ============================================================
-- Step 6: Create Updated Function
-- ============================================================
\echo '⚙️  Creating find_platform_matched_product_ids function...'

CREATE OR REPLACE FUNCTION find_platform_matched_product_ids(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.7,
  match_count int DEFAULT 3
)
RETURNS TABLE (
  product_id_internal INTEGER,
  product_name VARCHAR,
  product_style_id VARCHAR,
  style_id_normalized VARCHAR,
  platform VARCHAR,
  product_id_platform VARCHAR,
  platform_data JSONB,
  similarity float,
  embedding_text TEXT
)
LANGUAGE sql STABLE
AS $$
  SELECT
    p.product_id_internal,
    p.product_name_platform as product_name,
    p.style_id_platform as product_style_id,
    p.style_id_normalized,
    p.platform,
    p.product_id_platform,
    p.platform_data,
    1 - (p.embedding <=> query_embedding) as similarity,
    p.embedding_text
  FROM products p
  WHERE
    p.embedding IS NOT NULL
    AND p.product_name_platform IS NOT NULL
    AND p.product_name_platform != ''
    AND 1 - (p.embedding <=> query_embedding) > match_threshold
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

\echo '   ✓ Created find_platform_matched_product_ids function'
\echo ''

-- ============================================================
-- Summary
-- ============================================================
\echo '✅ Schema creation complete!'
\echo ''
\echo 'Created objects:'
\echo '  - products table (platform-agnostic with JSONB + embedding)'
\echo '  - product_id_internal as SERIAL PRIMARY KEY (auto-incrementing)'
\echo '  - 6 standard indexes'
\echo '  - 1 JSONB GIN index'
\echo '  - 1 vector index (ivfflat with cosine distance)'
\echo '  - find_platform_matched_product_ids function'
\echo ''
\echo 'Key design features:'
\echo '  • Platform column: stockx, alias, poizon (extensible)'
\echo '  • Descriptive column names: *_platform suffix'
\echo '  • JSONB column: platform_data for platform-specific fields'
\echo '  • Auto-incrementing product_id_internal'
\echo '  • Minimal constraints: only 3 required fields'
\echo ''
\echo 'Next step: Run migrate_products.py to populate data'
\echo ''
