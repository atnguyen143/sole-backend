# Migration Script Options

## Quick Reference

### migrate_products_v2.py (FAST)
- **Products:** ~1,792 (inventory-matched only)
- **Cost:** ~$0.03
- **Time:** 15-20 minutes
- **Use:** Quick test or inventory-only migration

### migrate_products_full.py (COMPLETE) ⭐ RECOMMENDED FOR OVERNIGHT
- **Products:** ~462,000 (ALL products from MySQL)
- **Cost:** ~$7.40
- **Time:** 8-12 hours
- **Use:** Complete migration of all StockX + Alias products

## What Each Migrates

### migrate_products_v2.py
- ✅ Phase 1: Inventory-matched products only (~1,792)
- ❌ Phase 2: Skipped
- ❌ Phase 3: Skipped

### migrate_products_full.py
- ✅ Phase 1: Inventory-matched products (~1,792)
- ✅ Phase 2: All StockX with styleId (~178,248)
- ✅ Phase 3: StockX without styleId + All Alias (~282,864)
- **Total:** ~462,000 products

## Windows VPS Commands

### For Overnight Run (All Products)
```powershell
cd C:\path\to\Local-Projects\sole-backend
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python migrate_products_full.py
```

### For Quick Test (Inventory Only)
```powershell
cd C:\path\to\Local-Projects\sole-backend
git pull origin main
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python migrate_products_v2.py
```

## Features (Both Scripts)
- ✅ Async insertion queue
- ✅ Real-time progress tracking
- ✅ Safe stop (Ctrl+C)
- ✅ Duplicate prevention
- ✅ Auto-resume (skips already migrated)
