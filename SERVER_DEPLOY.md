# Server Deployment Guide

## 1️⃣ On Your Local Machine (Push to Git)

```bash
cd /Users/anthonynguyen/notDesktop/Local-Projects/sole-backend

# Add all files
git add .

# Commit
git commit -m "Add migration V2 with async queue and safe stop"

# Push to remote
git push origin main
```

## 2️⃣ On Your Server (Pull & Setup)

### Pull Latest Code
```bash
cd /path/to/sole-backend  # Navigate to your sole-backend directory on server
git pull origin main
```

### Create Virtual Environment
```bash
# Create venv
python3 -m venv .venv

# Activate venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configure Environment Variables
Edit `.env` file with your credentials:
```bash
nano .env
```

Make sure these are set correctly:
```env
# OpenAI API
OPENAI_API_KEY=your_key_here

# MySQL Database
MYSQL_HOST=76.191.100.66
MYSQL_USER=se_assistant_bot_sole
MYSQL_PASSWORD=2hUzrmbAxeWJ
MYSQL_DATABASE=se_assistant

# Supabase
SUPABASE_HOST=db.rmufrqgptglonjwserbo.supabase.co
SUPABASE_DATABASE=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=IFELriNmzDW5PWgr
```

### Run Migration (with nohup for background)
```bash
# Make sure venv is activated
source .venv/bin/activate

# Run in background with nohup
nohup python migrate_products_v2.py > migration.log 2>&1 &

# Check progress
tail -f migration.log

# Or run in foreground with ability to Ctrl+C stop
python migrate_products_v2.py
```

### Check Progress in Real-Time
```bash
# Watch the log file
tail -f migration.log

# Check how many products inserted (in another terminal)
python -c "
import psycopg2
conn = psycopg2.connect(
    host='db.rmufrqgptglonjwserbo.supabase.co',
    database='postgres',
    user='postgres',
    password='IFELriNmzDW5PWgr',
    port=5432
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) as total FROM products')
print(f'Total products: {cur.fetchone()[0]}')
cur.execute('SELECT platform, COUNT(*) FROM products GROUP BY platform')
for row in cur.fetchall():
    print(f'{row[0]}: {row[1]}')
cur.close()
conn.close()
"
```

## 3️⃣ Features

✅ **Async Insertion Queue** - Products inserted immediately as embeddings generate
✅ **Safe Stop (Ctrl+C)** - Gracefully stops and saves progress
✅ **Real-time Progress** - Shows stats every 10 inserts
✅ **Error Handling** - Continues even if individual products fail

## 4️⃣ Expected Results

- **Phase 1**: ~1,792 inventory-matched products
- **935 StockX** products (matched to inventory)
- **857 Alias** products (matched to inventory)
- **Time**: ~30-40 minutes for full run

## 5️⃣ After Migration Complete

Run the vector index creation (if not already run):
```sql
-- In Supabase SQL Editor
CREATE INDEX idx_products_embedding_cosine
  ON products
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

Then run the search function (if not already created):
```sql
-- Already created from migration_sql_supabase_dashboard.sql
-- Just verify it exists
SELECT * FROM find_platform_matched_product_ids(
  (SELECT embedding FROM products LIMIT 1),
  0.7,
  3
);
```

## 🔥 Quick Commands Reference

```bash
# On local machine
cd /Users/anthonynguyen/notDesktop/Local-Projects/sole-backend
git add . && git commit -m "Migration ready" && git push

# On server
cd /path/to/sole-backend
git pull
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
nano .env  # Update credentials
nohup python migrate_products_v2.py > migration.log 2>&1 &
tail -f migration.log
```
