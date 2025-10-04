# Sole Backend - Product & Inventory Migration

## 📁 Project Structure

```
sole-backend/
├── scripts/
│   ├── active/          # Scripts you'll actually run
│   ├── testing/         # Scripts for testing/validation
│   └── deprecated/      # Old versions (kept for reference)
├── sql/                 # Database schemas
└── docs/                # Documentation
```

## 🚀 Active Scripts (Use These)

### 1. **run_overnight.py** - Full migration pipeline
Runs everything overnight:
- Fix existing 857 alias products
- Migrate 282K new alias products
- Create indexes

```bash
python scripts/active/run_overnight.py
```

### 2. **migrate_alias_remaining.py** - Migrate alias products
Migrates remaining alias products with:
- Batch embedding generation (500/request)
- Batch database inserts (500/query)
- Auto-updates inventory table

```bash
python scripts/active/migrate_alias_remaining.py
```

### 3. **regenerate_alias_embeddings.py** - Fix existing alias products
Regenerates embeddings for existing 857 alias products with cleaned format

```bash
python scripts/active/regenerate_alias_embeddings.py
```

### 4. **migrate_inventory_batch.py** - Migrate inventory
Batch migrates inventory from MySQL to Supabase

```bash
python scripts/active/migrate_inventory_batch.py
```

### 5. **create_product_mappings.py** - Link alias → stockx
Creates product_mapping table linking alias to canonical StockX products

```bash
python scripts/active/create_product_mappings.py
```

### 6. **create_vector_index_verbose.py** - Create similarity index
Creates vector index for fast similarity search (with progress output)

```bash
python scripts/active/create_vector_index_verbose.py
```

## 🧪 Testing Scripts

### **test_similarity_thresholds.py** - Test mapping confidence
Tests different similarity thresholds to find optimal setting

```bash
python scripts/testing/test_similarity_thresholds.py
```

### **product_search.py** - Search products
Test semantic product search

```bash
python scripts/testing/product_search.py
```

## 📊 Database Tables

### **products**
Unified product table (StockX + Alias)
- `platform`: 'stockx' or 'alias'
- `product_name_platform`: Uppercase product name
- `embedding_text`: Text used for embeddings (style_id + name)
- `embedding`: 1536-dim vector for similarity search

### **inventory**
Inventory table with snake_case columns
- `product_id_internal`: Links to products table
- `alias_catalog_id`: Legacy alias ID
- `stockx_product_id`: Legacy stockx ID

### **product_mapping**
Maps alias products → canonical StockX products
- `alias_product_id`: Alias product
- `stockx_product_id`: StockX product
- `is_default_alias`: Default alias for price search
- `confidence_score`: Match confidence (0.00-1.00)

## 📝 Common Workflows

### Full overnight migration
```bash
python scripts/active/run_overnight.py
```

### Just create product mappings
```bash
# 1. Create vector index first (faster searches)
python scripts/active/create_vector_index_verbose.py

# 2. Create mappings
python scripts/active/create_product_mappings.py
```

### Test similarity thresholds before mapping
```bash
python scripts/testing/test_similarity_thresholds.py
# Then update create_product_mappings.py with chosen threshold
```

## ⚙️ Configuration

All scripts use `.env` for configuration:
```env
MYSQL_HOST=...
MYSQL_USER=...
MYSQL_PASSWORD=...
SUPABASE_HOST=...
SUPABASE_USER=...
SUPABASE_PASSWORD=...
OPENAI_API_KEY=...
```

## 💰 Cost Estimates

- Alias migration (282K): ~$11.30
- Fix existing (857): ~$0.03
- Product mappings: $0 (reuses embeddings)
- Total: ~$11.33
