# Supabase Migration Plan: Platform-Agnostic Products Table

## Overview
Consolidate `products` and `product_embeddings` tables into a single unified platform-agnostic `products` table with:
- Auto-incrementing internal ID
- Platform column for extensibility
- JSONB for platform-specific data
- Minimal required fields

## Pre-Migration Checklist
- [ ] Backup current Supabase data
- [ ] Test migration on a copy/staging environment first
- [ ] Define Alias inventory matching query
- [ ] Ensure `.env` file has correct credentials

## Phase 1: Cleanup & Preparation

### Step 1.1: Drop Existing Indexes
```sql
-- Drop vector index on old table
DROP INDEX IF EXISTS idx_product_embeddings_cosine;

-- Drop any other indexes on products/product_embeddings
DROP INDEX IF EXISTS idx_products_style_id;
DROP INDEX IF EXISTS idx_products_name;
```

### Step 1.2: Drop Existing Functions
```sql
-- Drop old function (will recreate with new signature)
DROP FUNCTION IF EXISTS find_platform_matched_product_ids(vector, float, int);
DROP FUNCTION IF EXISTS find_platform_matched_product_ids;
```

### Step 1.3: Drop Existing Tables
```sql
-- Drop product_embeddings table (data will be consolidated)
DROP TABLE IF EXISTS product_embeddings CASCADE;

-- Drop old products table
DROP TABLE IF EXISTS products CASCADE;
```

## Phase 2: Create New Schema

### Step 2.1: Enable Vector Extension
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Step 2.2: Create New Products Table (Platform-Agnostic)
```sql
CREATE TABLE products (
  -- Primary Key (Internal Auto-Incrementing)
  product_id_internal SERIAL PRIMARY KEY,

  -- Platform IDs
  product_id_platform VARCHAR(255) NOT NULL UNIQUE,  -- Platform's product ID
  platform VARCHAR(50) NOT NULL,                     -- 'stockx', 'alias', 'poizon', etc.
  platform_id VARCHAR(255),                          -- RESERVED for future

  -- Core Product Information
  product_name_platform VARCHAR(512) NOT NULL,  -- Platform's product name
  style_id_platform VARCHAR(255),               -- Platform's style ID
  style_id_normalized VARCHAR(255),             -- Normalized for matching

  -- Platform-Specific Data (Flexible)
  platform_data JSONB,                          -- All platform-specific fields

  -- Embeddings
  embedding vector(1536),
  embedding_text TEXT,

  -- Metadata
  keyword_used TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- Constraints (minimal)
  CONSTRAINT products_name_check CHECK (product_name_platform IS NOT NULL AND product_name_platform != ''),
  CONSTRAINT products_platform_check CHECK (platform IN ('stockx', 'alias', 'poizon'))
);
```

**Note:** Only `product_id_internal`, `product_id_platform`, `platform`, and `product_name_platform` are required. Everything else is nullable.

### Step 2.3: Create Indexes
```sql
-- Standard indexes
CREATE INDEX idx_products_platform ON products(platform);
CREATE INDEX idx_products_product_id_platform ON products(product_id_platform);
CREATE INDEX idx_products_style_id_platform ON products(style_id_platform);
CREATE INDEX idx_products_style_id_normalized ON products(style_id_normalized);
CREATE INDEX idx_products_name_platform ON products(product_name_platform);
CREATE INDEX idx_products_platform_composite ON products(platform, product_id_platform);

-- JSONB index
CREATE INDEX idx_products_platform_data ON products USING GIN (platform_data);

-- Vector index
SET maintenance_work_mem = '128MB';
CREATE INDEX idx_products_embedding_cosine
  ON products
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
RESET maintenance_work_mem;
```

### Step 2.4: Create Updated Function
```sql
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
```

## Phase 3: Data Migration (Phased Approach)

### Migration Strategy: 3 Phases

#### **Phase 3.1: Inventory-Relevant Products (PRIORITY)**

**StockX - Inventory Subset:**
```sql
SELECT DISTINCT sp.*
FROM stockx_products sp
JOIN (
    SELECT
        item,
        SUBSTRING_INDEX(SUBSTRING_INDEX(item, '[', -1), ']', 1) AS extracted_styleId
    FROM inventory
    WHERE item LIKE '%[%]%'
) i
ON sp.styleId = i.extracted_styleId
```

**Alias - Inventory Subset:**
```sql
-- TODO: Define how to match Alias products with inventory
-- Examples:
-- - By product name similarity?
-- - By SKU pattern?
-- - By manual mapping table?
```

#### **Phase 3.2: Remaining Products WITH Style IDs**

**StockX - Exclude Already Migrated:**
```sql
SELECT *
FROM stockx_products
WHERE styleId IS NOT NULL
  AND styleId != ''
  AND productId NOT IN (
    SELECT product_id_platform
    FROM products
    WHERE platform = 'stockx'
  )
```

**Alias - With Style ID (if extractable):**
```sql
-- Alias typically doesn't have style IDs
-- Include only if you have logic to extract them
```

#### **Phase 3.3: Products WITHOUT Style IDs (Lower Priority)**

**StockX - No Style ID, Exclude Migrated:**
```sql
SELECT *
FROM stockx_products
WHERE (styleId IS NULL OR styleId = '')
  AND productId NOT IN (
    SELECT product_id_platform
    FROM products
    WHERE platform = 'stockx'
  )
```

**Alias - Remaining, Exclude Migrated:**
```sql
SELECT *
FROM alias_products
WHERE catalogId NOT IN (
    SELECT product_id_platform
    FROM products
    WHERE platform = 'alias'
  )
```

### Data Transformation Examples

**StockX Product → Supabase:**
```python
{
  'product_id_platform': stockx.productId,
  'platform': 'stockx',
  'platform_id': None,
  'product_name_platform': stockx.title,
  'style_id_platform': stockx.styleId,
  'style_id_normalized': normalize_style_id(stockx.styleId),
  'platform_data': {
    'brand': stockx.brand,
    'gender': stockx.productAttributes_gender,
    'retailPrice': stockx.productAttributes_retailPrice,
    'imageLink': stockx.imageLink,
    'colorway': stockx.productAttributes_colorway,
    # ... all other StockX fields
  },
  'embedding': generate_embedding(embedding_text),
  'embedding_text': f"STYLEID: {styleId} PRODUCT_NAME: {clean_title}"
}
```

**Alias Product → Supabase:**
```python
{
  'product_id_platform': alias.catalogId,
  'platform': 'alias',
  'platform_id': None,
  'product_name_platform': alias.name,
  'style_id_platform': None,  # Alias doesn't have style IDs
  'style_id_normalized': None,
  'platform_data': {
    'sku': alias.sku,
    'gender': alias.gender
  },
  'embedding': generate_embedding(embedding_text),
  'embedding_text': f"PRODUCT_NAME: {clean_name}"
}
```

## Phase 4: Verification

### Step 4.1: Data Verification Queries
```sql
-- Count total products
SELECT COUNT(*) FROM products;

-- Count by platform
SELECT platform, COUNT(*)
FROM products
GROUP BY platform;

-- Count products with embeddings
SELECT COUNT(*)
FROM products
WHERE embedding IS NOT NULL;

-- Check for duplicates (should be 0)
SELECT product_id_platform, COUNT(*)
FROM products
GROUP BY product_id_platform
HAVING COUNT(*) > 1;

-- Test vector search
SELECT * FROM find_platform_matched_product_ids(
  (SELECT embedding FROM products LIMIT 1),
  0.7,
  5
);
```

### Step 4.2: Platform-Specific Queries
```sql
-- Query StockX products by brand (using JSONB)
SELECT
  product_id_platform,
  product_name_platform,
  platform_data->>'brand' as brand
FROM products
WHERE platform = 'stockx'
  AND platform_data->>'brand' = 'Nike'
LIMIT 10;

-- Get all platforms for a style_id
SELECT
  platform,
  product_id_platform,
  product_name_platform
FROM products
WHERE style_id_normalized = 'DZ5485612'
ORDER BY platform;
```

## Phase 5: Application Code Updates

### Old Code Pattern (to replace):
```python
# OLD - Platform-specific columns
stockx_id = match.get("stockx_productid")
alias_id = match.get("alias_catalogid")
```

### New Code Pattern:
```python
# NEW - Platform-based filtering
matches = find_platform_matched_product_ids(embedding, 0.7, 10)

for match in matches:
    if match['platform'] == 'stockx':
        stockx_id = match['product_id_platform']
        # Access platform data
        brand = match['platform_data'].get('brand')
        image_url = match['platform_data'].get('imageLink')

    elif match['platform'] == 'alias':
        alias_id = match['product_id_platform']
        # Access platform data
        sku = match['platform_data'].get('sku')
```

### Files to Update:
1. `/discord-bot/ai_agents/mcp_tool_agent.py` - Update result handling
2. `/discord-bot/commands/inventory.py` - Update enrichment logic
3. `/discord-bot/commands/AIEngine.py` - Update display logic
4. `/discord-bot/commands/market.py` - Update data formatting
5. `/discord-bot/docs/important/ai_business_context.md` - Update docs

## Phase 6: Rollback Plan

### Backup Before Migration:
```bash
pg_dump -h aws-1-us-east-2.pooler.supabase.com \
  -U postgres.rmufrqgptglonjwserbo \
  -d postgres \
  -t products \
  -t product_embeddings \
  > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Restore If Needed:
```bash
psql -h aws-1-us-east-2.pooler.supabase.com \
  -U postgres.rmufrqgptglonjwserbo \
  -d postgres \
  < backup_YYYYMMDD_HHMMSS.sql
```

## Migration Execution Order

1. ✅ **Phase 1**: Cleanup (sql/01_cleanup.sql)
2. ✅ **Phase 2**: Create Schema (sql/02_create_schema.sql)
3. ✅ **Phase 3**: Run Migration
   - 3.1: `python migrate_products.py` (Phase 1 - Inventory only)
   - 3.2: Uncomment Phase 2 in script, run again
   - 3.3: Uncomment Phase 3 in script, run again
4. ✅ **Phase 4**: Verify (sql/03_verify.sql)
5. ✅ **Phase 5**: Update application code
6. ✅ **Phase 6**: Test in production

## Key Design Benefits

✅ **No Duplicates**: Exclusion logic in queries prevents duplicate migrations
✅ **Platform Agnostic**: Add new platforms without schema changes
✅ **Minimal Schema**: Only 12 columns, most nullable
✅ **Flexible**: JSONB stores platform-specific fields
✅ **Phased Migration**: Migrate in stages (inventory → with style_id → without)
✅ **Auto-ID**: Internal ID for future relationships

## Notes

- `product_name_platform` and `style_id_platform` clarify source
- Most fields nullable except: `product_id_platform`, `platform`, `product_name_platform`
- Use JSONB queries for platform-specific fields
- Function returns platform-agnostic results
- Application code filters by platform as needed
