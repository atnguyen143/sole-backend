"""
MASTER MIGRATION - BATCH API VERSION
=====================================

Complete migration using OpenAI Batch API (50% cheaper)

Steps:
1. Insert all products to Supabase (NO embeddings) - FAST (2-5 min)
2. Submit batch job to OpenAI for embeddings - CHEAP (24hr, $9)
3. Poll batch status and update Supabase when ready
4. Create vector index (requires Supabase compute upgrade)

Total cost: ~$9 (vs $18 sync)
Total time: ~24 hours (hands-off)
"""

import os
import sys

print("\n" + "="*80)
print("MASTER MIGRATION - BATCH API VERSION")
print("="*80)
print("\nThis workflow:")
print("1️⃣  Insert all products (2-5 min, $0)")
print("2️⃣  Submit batch embeddings job (instant, ~$9)")
print("3️⃣  Wait 24 hours (automatic)")
print("4️⃣  Download & update embeddings (5 min, $0)")
print("5️⃣  Create vector index (requires MEDIUM compute)")
print("\n💰 Total cost: ~$9 (50% off)")
print("⏱️  Total time: ~24 hours (hands-off)")
print("="*80 + "\n")

response = input("Which step? (1=insert products, 2=submit batch, 3=check & update, 4=create index): ")

if response == '1':
    print("\n🚀 Running: Insert all products (no embeddings)\n")
    os.system('python scripts/active/insert_all_products_no_embeddings.py')

elif response == '2':
    print("\n🚀 Running: Submit batch embeddings job\n")
    os.system('python scripts/active/batch_generate_embeddings.py')

elif response == '3':
    print("\n🚀 Running: Check batch status & update Supabase\n")
    os.system('python scripts/active/batch_generate_embeddings.py')

elif response == '4':
    print("\n🚀 Creating vector index\n")
    print("Run this SQL in Supabase SQL Editor:\n")
    print("SET maintenance_work_mem = '512MB';")
    print("CREATE INDEX idx_products_embedding ON products")
    print("USING ivfflat (embedding vector_cosine_ops)")
    print("WITH (lists = 679);  -- sqrt(461000)")
    print("\nMake sure you've upgraded to MEDIUM compute first!")

else:
    print("❌ Invalid option")
