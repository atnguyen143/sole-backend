# Windows VPS Deployment Guide (PowerShell)

## 1️⃣ On Your Local Machine (Push to Git)

Already done! ✅ Code is pushed to GitHub.

## 2️⃣ On Your Windows VPS (PowerShell)

### Clone Repository (First Time Only)
```powershell
# Navigate to where you want the project
cd C:\Users\YourUsername\  # Or wherever you want

# Clone the repository
git clone https://github.com/atnguyen143/Local-Projects.git

# Navigate to sole-backend
cd Local-Projects\sole-backend
```

### OR Pull Latest (If Already Cloned)
```powershell
cd C:\path\to\Local-Projects\sole-backend
git pull origin main
```

### Create Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (PowerShell)
.\.venv\Scripts\Activate.ps1

# If you get execution policy error, run this first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then activate again
.\.venv\Scripts\Activate.ps1
```

### Install Dependencies
```powershell
# Make sure venv is activated (you should see (.venv) in prompt)
pip install -r requirements.txt
```

### Configure Environment Variables
Create/edit `.env` file:
```powershell
notepad .env
```

Add these contents:
```env
# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# MySQL Database
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database

# Supabase
SUPABASE_HOST=your_supabase_host
SUPABASE_DATABASE=postgres
SUPABASE_USER=postgres
SUPABASE_PASSWORD=your_supabase_password
SUPABASE_MAX_CONNECTIONS=5
```

### Run Migration

#### Option A: Run in Background (Recommended)
```powershell
# Start migration in background job
Start-Job -ScriptBlock {
    Set-Location "C:\path\to\Local-Projects\sole-backend"
    .\.venv\Scripts\Activate.ps1
    python migrate_products_v2.py
} -Name "MigrationJob" | Out-File migration.log

# Check status
Get-Job -Name "MigrationJob"

# View output
Receive-Job -Name "MigrationJob" -Keep

# Stop job if needed
Stop-Job -Name "MigrationJob"
Remove-Job -Name "MigrationJob"
```

#### Option B: Run in Foreground (Simple, Can Ctrl+C)
```powershell
# Make sure venv is activated
.\.venv\Scripts\Activate.ps1

# Run migration
python migrate_products_v2.py

# Press Ctrl+C to stop gracefully
```

#### Option C: Run with Output to File
```powershell
# Redirect output to file
python migrate_products_v2.py > migration.log 2>&1

# Watch log in another PowerShell window
Get-Content migration.log -Wait -Tail 50
```

### Check Progress in Real-Time
```powershell
# In another PowerShell window
.\.venv\Scripts\Activate.ps1

python -c @"
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
"@
```

## 🔥 Quick Copy-Paste Commands

### First Time Setup
```powershell
# Clone repo
cd C:\Users\YourUsername
git clone https://github.com/atnguyen143/Local-Projects.git
cd Local-Projects\sole-backend

# Setup venv
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Create .env
notepad .env
# Paste the credentials from above, save and close

# Run migration
python migrate_products_v2.py
```

### If Already Have Code (Just Update)
```powershell
cd C:\path\to\Local-Projects\sole-backend
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python migrate_products_v2.py
```

## 🎯 Expected Results

- **~1,792 products** processed
- **935 StockX** + **857 Alias** products
- **30-40 minutes** total runtime
- Real-time insertion as embeddings generate
- Can stop with Ctrl+C anytime

## 📊 Monitoring

### Check Products Count
```powershell
.\.venv\Scripts\Activate.ps1
python -c "import psycopg2; conn = psycopg2.connect(host='db.rmufrqgptglonjwserbo.supabase.co', database='postgres', user='postgres', password='IFELriNmzDW5PWgr', port=5432); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM products'); print(f'Total: {cur.fetchone()[0]}'); cur.close(); conn.close()"
```

### View Migration Log (if running in background)
```powershell
Get-Content migration.log -Wait -Tail 50
```

## ⚠️ Troubleshooting

### If you get "script cannot be loaded" error:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### If Python not found:
```powershell
# Check Python is installed
python --version

# If not, download from python.org and install
# Make sure to check "Add Python to PATH" during installation
```

### If Git not found:
```powershell
# Download Git for Windows from git-scm.com
# Or use:
winget install Git.Git
```
