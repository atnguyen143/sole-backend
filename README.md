# Sole Backend - Supabase Migration

This directory contains all files needed to migrate your product data from MySQL to Supabase with a redesigned schema.

## Files

### Documentation
- **`SCHEMA_CONTEXT.md`** - Complete database schema documentation
  - MySQL table structures (inventory, stockx_products, stockx_variants, alias_products)
  - Current Supabase schema
  - New Supabase schema design
  - Data mapping strategy

- **`MIGRATION_PLAN.md`** - Detailed step-by-step migration plan
  - Phase 1: Cleanup (drop old tables/indexes/functions)
  - Phase 2: Create new schema
  - Phase 3: Data migration
  - Phase 4: Verification
  - Phase 5: Application code updates
  - Phase 6: Rollback plan

### Configuration
- **`.env`** - Database credentials (DO NOT COMMIT TO GIT)
  - OpenAI API key
  - MySQL connection details
  - Supabase connection details

- **`CLAUDE.md`** - Claude Code configuration

### Scripts
- **`migrate_products.py`** - Main migration script
  - Fetches data from MySQL
  - Generates embeddings
  - Inserts into Supabase

- **`sql/01_cleanup.sql`** - Drop existing tables/functions/indexes
- **`sql/02_create_schema.sql`** - Create new products table and function
- **`sql/03_verify.sql`** - Verification queries

## Key Changes

### Column Renaming (Platform-First Convention)
| Old Name | New Name |
|----------|----------|
| `stockx_productid` | `product_id_stockx` |
| `alias_catalogid` | `product_id_alias` |

### New Columns
- `product_id_internal` - Reserved for future use
- `style_id_normalized` - Normalized style IDs for better matching
- `embedding` - Consolidated from separate `product_embeddings` table
- `embedding_text` - Stores text used to generate embeddings

### Removed Tables
- `product_embeddings` - Consolidated into `products` table

## Quick Start

### 1. Install Dependencies
```bash
pip install psycopg2-binary pymysql python-dotenv openai
```

### 2. Configure Environment
Edit `.env` file with your credentials (already populated with your info)

### 3. Run SQL Cleanup (CAREFUL - This deletes data!)
```bash
psql -h aws-1-us-east-2.pooler.supabase.com \
  -U postgres.rmufrqgptglonjwserbo \
  -d postgres \
  -f sql/01_cleanup.sql
```

### 4. Create New Schema
```bash
psql -h aws-1-us-east-2.pooler.supabase.com \
  -U postgres.rmufrqgptglonjwserbo \
  -d postgres \
  -f sql/02_create_schema.sql
```

### 5. Run Migration Script
```bash
python migrate_products.py
```

### 6. Verify Migration
```bash
psql -h aws-1-us-east-2.pooler.supabase.com \
  -U postgres.rmufrqgptglonjwserbo \
  -d postgres \
  -f sql/03_verify.sql
```

### 7. Update Application Code
See `MIGRATION_PLAN.md` Phase 5 for files to update

## Important Notes

⚠️ **BACKUP FIRST**: Always backup your Supabase data before running cleanup script

⚠️ **TEST IN STAGING**: Test this migration in a staging environment first

⚠️ **RATE LIMITS**: OpenAI embedding generation may take time depending on product count

⚠️ **PASSWORD IN .env**: Your Supabase password contains special characters. The connection string is already properly formatted.

## Migration Timeline

- **Cleanup**: 5 minutes
- **Schema Creation**: 10 minutes
- **Data Migration**: 30-60 minutes (depends on product count & OpenAI rate limits)
- **Verification**: 10 minutes
- **Code Updates**: 30 minutes
- **Total**: ~1.5-2 hours

## Next Steps After Migration

1. Update application code (see Phase 5 in MIGRATION_PLAN.md)
2. Update MCP server to use new column names
3. Test vector search functionality
4. Monitor performance and adjust indexes if needed

## Support

For issues or questions:
1. Check MIGRATION_PLAN.md for detailed troubleshooting
2. Review SCHEMA_CONTEXT.md for schema details
3. Examine migrate_products.py for migration logic
