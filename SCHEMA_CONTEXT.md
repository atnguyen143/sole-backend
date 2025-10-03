# Database Schema Context

## MySQL Schemas (Source Data)

### 1. inventory Table
**Primary inventory tracking table**
```sql
CREATE TABLE `inventory` (
  `sold` tinyint(1) NOT NULL DEFAULT '0',
  `sku` varchar(100) NOT NULL PRIMARY KEY,
  `datePurchase` date DEFAULT NULL,
  `placeOfPurchase` varchar(255) DEFAULT NULL,
  `item` varchar(512) DEFAULT NULL,
  `size` varchar(50) DEFAULT NULL,
  `costPrice` decimal(10,2) DEFAULT NULL,
  `salesTax` decimal(10,2) DEFAULT NULL,
  `additionalCost` decimal(10,2) DEFAULT NULL,
  `paymentMethod` varchar(100) DEFAULT NULL,
  `rebate` decimal(10,2) DEFAULT NULL,
  `totalCost` decimal(10,2) DEFAULT NULL,
  `location` varchar(255) DEFAULT NULL,
  `referenceNumber` varchar(255) DEFAULT NULL,
  `comment` text,
  `deliveryDate` date DEFAULT NULL,
  `refundDate` date DEFAULT NULL,
  `verificationDate` date DEFAULT NULL,
  `salesTaxRefunded` tinyint(1) DEFAULT NULL,
  `plannedSalesMethod` varchar(100) DEFAULT NULL,
  `createdAt` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `stockx_productId` varchar(255) DEFAULT NULL,
  `stockx_variantId` varchar(255) DEFAULT NULL,
  `styleId` varchar(255) DEFAULT NULL,
  `poolId` varchar(255) DEFAULT NULL,
  `updatedVia` varchar(255) DEFAULT NULL,
  `saleTrackerRowIndex` varchar(255) DEFAULT NULL,
  `poolKey` varchar(255) DEFAULT NULL,
  `salesTaxRefundDepositDate` date DEFAULT NULL,
  `salesTaxRefundDepositAccount` varchar(255) DEFAULT NULL
);
```

### 2. stockx_products Table
**StockX product catalog**
```sql
CREATE TABLE `stockx_products` (
  `productId` varchar(255) NOT NULL PRIMARY KEY,
  `title` varchar(255) DEFAULT NULL,
  `productType` varchar(255) DEFAULT NULL,
  `styleId` varchar(255) DEFAULT NULL,
  `urlKey` varchar(255) DEFAULT NULL,
  `brand` varchar(255) DEFAULT NULL,
  `imageLink` varchar(255) DEFAULT NULL,
  `productAttributes_gender` varchar(50) DEFAULT NULL,
  `productAttributes_season` varchar(50) DEFAULT NULL,
  `productAttributes_releaseDate` date DEFAULT NULL,
  `productAttributes_retailPrice` decimal(10,2) DEFAULT NULL,
  `productAttributes_colorway` varchar(255) DEFAULT NULL,
  `productAttributes_color` varchar(255) DEFAULT NULL,
  `keywordUsed` text,
  `createdAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updatedAt` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3. stockx_variants Table
**StockX product variants (sizes)**
```sql
CREATE TABLE `stockx_variants` (
  `variantId` varchar(255) NOT NULL PRIMARY KEY,
  `variantValue` varchar(255) DEFAULT NULL,
  `productId` varchar(255) DEFAULT NULL,
  `defaultSize` varchar(50) DEFAULT NULL,
  `defaultSizeType` varchar(50) DEFAULT NULL,
  KEY `idx_variantId` (`variantId`),
  KEY `idx_productId` (`productId`),
  KEY `idx_variantValue` (`variantValue`),
  FOREIGN KEY (`productId`) REFERENCES `stockx_products` (`productId`) ON DELETE CASCADE
);
```

### 4. alias_products Table
**Alias/GOAT product catalog**
```sql
CREATE TABLE `alias_products` (
  `catalogId` varchar(255) NOT NULL PRIMARY KEY,
  `name` varchar(255) NOT NULL,
  `sku` varchar(255) DEFAULT NULL,
  `gender` varchar(50) DEFAULT NULL,
  `keywordUsed` varchar(255) DEFAULT NULL,
  `createdAt` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updatedAt` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY `idx_alias_products_name_sku_catalogId` (`name`,`sku`,`catalogId`)
);
```

## Current Supabase Schema

### Current products Table (DEPRECATED - To be replaced)
**Current structure based on code analysis:**
- Has separate `products` and `product_embeddings` tables
- `product_embeddings` table structure:
  - `embedding_1536` column (vector type)
  - Indexed with: `idx_product_embeddings_cosine` using ivfflat

### Current Function: find_platform_matched_product_ids
**Returns:**
- `product_name` - Product name
- `product_style_id` - Style ID
- `platform_name` - Platform identifier
- `stockx_productid` - StockX product ID (DEPRECATED)
- `alias_catalogid` - Alias catalog ID (DEPRECATED)
- `similarity` - Vector similarity score

## New Supabase Schema Design

### Design Philosophy
- **Platform-Agnostic**: Uses `platform` column instead of platform-specific ID columns
- **Minimal Core Fields**: Only common fields between all platforms (name, style_id)
- **JSON Storage**: Platform-specific data stored in JSONB column
- **Future-Proof**: Can accommodate new platforms (Poizon, eBay, etc.) without schema changes

### NEW products Table (Unified with Embeddings)

```sql
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

-- Indexes
CREATE INDEX idx_products_platform ON products(platform);
CREATE INDEX idx_products_product_id_platform ON products(product_id_platform);
CREATE INDEX idx_products_style_id_platform ON products(style_id_platform);
CREATE INDEX idx_products_style_id_normalized ON products(style_id_normalized);
CREATE INDEX idx_products_name_platform ON products(product_name_platform);
CREATE INDEX idx_products_platform_composite ON products(platform, product_id_platform);

-- GIN Index for JSONB queries
CREATE INDEX idx_products_platform_data ON products USING GIN (platform_data);

-- Vector Index
SET maintenance_work_mem = '128MB';
CREATE INDEX idx_products_embedding_cosine
  ON products
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
RESET maintenance_work_mem;
```

### NEW find_platform_matched_product_ids Function

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

**Note:** Application code can then filter by platform in the results:
```python
# Get all matches
matches = find_platform_matched_product_ids(embedding, 0.7, 10)

# Filter for specific platforms
stockx_matches = [m for m in matches if m['platform'] == 'stockx']
alias_matches = [m for m in matches if m['platform'] == 'alias']
```

## Migration Impact Analysis

### Tables to DROP:
1. `product_embeddings` - Consolidated into `products` table
2. Old `products` table (if exists with different schema)

### Functions to DROP:
1. Old `find_platform_matched_product_ids` function

### Indexes to DROP:
1. `idx_product_embeddings_cosine` on `product_embeddings` table
2. Any indexes on old `products` table

### Functions to RECREATE:
1. `find_platform_matched_product_ids` - Updated to work with new schema

### Application Code Updates Required:
**Files referencing old column names:**
- Change from platform-specific lookups to platform-based filtering
- Example old code:
  ```python
  stockx_id = match.get("stockx_productid")
  alias_id = match.get("alias_catalogid")
  ```
- Example new code:
  ```python
  if match['platform'] == 'stockx':
      stockx_id = match['product_id_platform']
  elif match['platform'] == 'alias':
      alias_id = match['product_id_platform']
  ```

## Data Mapping Strategy

### From MySQL to Supabase:

#### StockX Products:
```python
{
  'product_id_platform': stockx_products.productId,
  'platform': 'stockx',
  'platform_id': None,  # Reserved
  'product_name_platform': stockx_products.title,
  'style_id_platform': stockx_products.styleId,
  'style_id_normalized': normalize_style_id(stockx_products.styleId),
  'platform_data': {
    # Store ALL StockX-specific fields as JSON
    'productType': stockx_products.productType,
    'urlKey': stockx_products.urlKey,
    'brand': stockx_products.brand,
    'imageLink': stockx_products.imageLink,
    'gender': stockx_products.productAttributes_gender,
    'season': stockx_products.productAttributes_season,
    'releaseDate': stockx_products.productAttributes_releaseDate,
    'retailPrice': stockx_products.productAttributes_retailPrice,
    'colorway': stockx_products.productAttributes_colorway,
    'color': stockx_products.productAttributes_color
  },
  'keyword_used': stockx_products.keywordUsed,
  'embedding': generate_embedding(embedding_text),
  'embedding_text': f"STYLEID: {styleId} PRODUCT_NAME: {clean_title}"
}
```

#### Alias Products:
```python
{
  'product_id_platform': alias_products.catalogId,
  'platform': 'alias',
  'platform_id': None,  # Reserved
  'product_name_platform': alias_products.name,
  'style_id_platform': None,  # Alias doesn't provide style IDs
  'style_id_normalized': None,
  'platform_data': {
    # Store ALL Alias-specific fields as JSON
    'sku': alias_products.sku,
    'gender': alias_products.gender
  },
  'keyword_used': alias_products.keywordUsed,
  'embedding': generate_embedding(embedding_text),
  'embedding_text': f"PRODUCT_NAME: {clean_name}"
}
```

### Querying platform_data Examples:

```sql
-- Get all StockX products with brand 'Nike'
SELECT * FROM products
WHERE platform = 'stockx'
  AND platform_data->>'brand' = 'Nike';

-- Get products with retail price > $200
SELECT * FROM products
WHERE platform = 'stockx'
  AND (platform_data->>'retailPrice')::decimal > 200;

-- Get Alias products by gender
SELECT * FROM products
WHERE platform = 'alias'
  AND platform_data->>'gender' = 'men';
```

## Style ID Normalization Rules

```python
def normalize_style_id(style_id: str) -> str:
    """
    Normalize style IDs for better matching
    - Remove dashes, spaces, underscores
    - Convert to uppercase
    - Remove leading zeros (except standalone '0')
    """
    if not style_id:
        return None

    # Remove common separators
    normalized = style_id.replace('-', '').replace(' ', '').replace('_', '')

    # Convert to uppercase
    normalized = normalized.upper()

    # Remove leading zeros (but keep if it's just "0")
    if normalized and normalized != '0':
        normalized = normalized.lstrip('0') or '0'

    return normalized
```

## Benefits of New Design

1. **Extensibility**: Add new platforms without schema changes
2. **Simplicity**: Only 8 core columns (vs 20+ before)
3. **Flexibility**: Platform-specific data in JSONB
4. **Performance**: Indexed platform + product_id for fast lookups
5. **Future-Proof**: Reserved platform_id column for internal IDs
6. **Clean API**: Application code filters by platform instead of checking multiple ID columns
