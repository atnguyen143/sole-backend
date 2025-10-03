"""
Supabase Products Migration - FULL (All Phases)

Migrates ALL products from MySQL to Supabase:
- Phase 1: Inventory-matched products (PRIORITY) ~1,792 products
- Phase 2: All StockX products with styleId ~178,248 products
- Phase 3: All StockX without styleId + All Alias ~282,864 products
- Total: ~462K products

Estimated Cost: ~$7.40 (text-embedding-3-small @ $0.020/1M tokens)
Runtime: ~8-12 hours

Features:
- Async insertion queue
- Safe stop (Ctrl+C)
- Duplicate prevention
- Real-time progress
"""

import os
import time
import json
import pymysql
import psycopg2
import signal
import sys
from typing import List, Dict, Optional
from queue import Queue
from threading import Thread, Event
from dotenv import load_dotenv
import openai

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
}
SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}

client = openai.OpenAI(api_key=OPENAI_API_KEY)
stop_event = Event()
stats = {'generated': 0, 'inserted': 0, 'failed': 0, 'skipped': 0}

def signal_handler(sig, frame):
    print("\n\n⚠️  Stopping gracefully... (Ctrl+C again to force quit)")
    stop_event.set()

signal.signal(signal.SIGINT, signal_handler)

# ==================== UTILITIES ====================

def normalize_style_id(style_id: str) -> Optional[str]:
    if not style_id or str(style_id).strip() == '':
        return None
    normalized = str(style_id).replace('-', '').replace(' ', '').replace('_', '')
    normalized = normalized.upper()
    if normalized != '0':
        normalized = normalized.lstrip('0') or '0'
    return normalized if normalized else None

def normalize_text_for_embedding(text: str) -> str:
    if not text:
        return ""
    return text.replace("_", "").replace("-", "")

def generate_embedding_text_stockx(title: str, style_id: Optional[str] = None) -> str:
    normalized_title = normalize_text_for_embedding(title) if title else ""
    if style_id:
        normalized_style_id = normalize_text_for_embedding(style_id)
        return f"{normalized_style_id} {normalized_title}".strip()
    return normalized_title

def generate_embedding_text_alias(name: str, sku: Optional[str] = None) -> str:
    normalized_name = normalize_text_for_embedding(name) if name else ""
    if sku:
        normalized_sku = normalize_text_for_embedding(sku)
        return f"{normalized_name} {normalized_sku}".strip()
    return normalized_name

def generate_embedding(text: str, retry_count: int = 3) -> Optional[List[float]]:
    for attempt in range(retry_count):
        if stop_event.is_set():
            return None
        try:
            response = client.embeddings.create(input=text, model="text-embedding-3-small")
            return response.data[0].embedding
        except Exception as e:
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)
            else:
                return None
    return None

# ==================== DATA FETCHING ====================

def fetch_stockx_inventory_subset() -> List[Dict]:
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    query = """
        SELECT DISTINCT sp.*
        FROM stockx_products sp
        JOIN (
            SELECT item, SUBSTRING_INDEX(SUBSTRING_INDEX(item, '[', -1), ']', 1) AS extracted_styleId
            FROM inventory WHERE item LIKE '%[%]%'
        ) i ON sp.styleId = i.extracted_styleId
    """
    cursor.execute(query)
    results = cursor.fetchall()
    print(f"\n✅ StockX Inventory Query - Sample verification:")
    if results:
        print(f"   {results[0].get('title', 'N/A')} | Style ID: {results[0].get('styleId', 'N/A')}")
    cursor.close()
    conn.close()
    return results

def fetch_alias_inventory_subset() -> List[Dict]:
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    query = """
        SELECT DISTINCT ap.*
        FROM alias_products ap
        JOIN (
            SELECT item, REPLACE(SUBSTRING_INDEX(SUBSTRING_INDEX(item, '[', -1), ']', 1), '-', ' ') AS extracted_styleId
            FROM inventory WHERE item LIKE '%[%]%'
        ) i ON ap.sku = i.extracted_styleId
    """
    cursor.execute(query)
    results = cursor.fetchall()
    print(f"\n✅ Alias Inventory Query - Sample verification:")
    if results:
        print(f"   {results[0].get('name', 'N/A')} | SKU: {results[0].get('sku', 'N/A')}")
    cursor.close()
    conn.close()
    return results

def get_migrated_ids(platform: str) -> set:
    """Get already migrated product IDs from Supabase"""
    try:
        conn = psycopg2.connect(**SUPABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT product_id_platform FROM products WHERE platform = %s", (platform,))
        migrated_ids = {row[0] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return migrated_ids
    except:
        return set()

def fetch_stockx_with_style_id_exclude_migrated() -> List[Dict]:
    migrated_ids = get_migrated_ids('stockx')
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("""
        SELECT * FROM stockx_products
        WHERE styleId IS NOT NULL AND styleId != ''
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r for r in results if r['productId'] not in migrated_ids]

def fetch_stockx_without_style_id_exclude_migrated() -> List[Dict]:
    migrated_ids = get_migrated_ids('stockx')
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("""
        SELECT * FROM stockx_products
        WHERE styleId IS NULL OR styleId = ''
    """)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r for r in results if r['productId'] not in migrated_ids]

def fetch_alias_exclude_migrated() -> List[Dict]:
    migrated_ids = get_migrated_ids('alias')
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM alias_products")
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return [r for r in results if r['catalogId'] not in migrated_ids]

# ==================== TRANSFORMATION ====================

def transform_stockx_product(product: Dict) -> Dict:
    style_id = product.get('styleId')
    product_name = product.get('title', '')
    platform_data = {
        'productType': product.get('productType'),
        'urlKey': product.get('urlKey'),
        'brand': product.get('brand'),
        'imageLink': product.get('imageLink'),
        'gender': product.get('productAttributes_gender'),
        'season': product.get('productAttributes_season'),
        'releaseDate': str(product.get('productAttributes_releaseDate')) if product.get('productAttributes_releaseDate') else None,
        'retailPrice': float(product.get('productAttributes_retailPrice')) if product.get('productAttributes_retailPrice') else None,
        'colorway': product.get('productAttributes_colorway'),
        'color': product.get('productAttributes_color')
    }
    return {
        'product_id_platform': product.get('productId'),
        'platform': 'stockx',
        'platform_id': None,
        'product_name_platform': product_name,
        'style_id_platform': style_id,
        'style_id_normalized': normalize_style_id(style_id),
        'platform_data': json.dumps(platform_data),
        'keyword_used': product.get('keywordUsed'),
        'embedding': None,
        'embedding_text': generate_embedding_text_stockx(product_name, style_id)
    }

def transform_alias_product(product: Dict) -> Dict:
    product_name = product.get('name', '')
    sku = product.get('sku')
    platform_data = {'sku': sku, 'gender': product.get('gender')}
    return {
        'product_id_platform': product.get('catalogId'),
        'platform': 'alias',
        'platform_id': None,
        'product_name_platform': product_name,
        'style_id_platform': None,
        'style_id_normalized': None,
        'platform_data': json.dumps(platform_data),
        'keyword_used': product.get('keywordUsed'),
        'embedding': None,
        'embedding_text': generate_embedding_text_alias(product_name, sku)
    }

# ==================== ASYNC QUEUE ====================

def insert_worker(queue: Queue):
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cursor = conn.cursor()
    insert_query = """
        INSERT INTO products (
            product_id_platform, platform, platform_id,
            product_name_platform, style_id_platform, style_id_normalized,
            platform_data, embedding, embedding_text, keyword_used
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (product_id_platform) DO UPDATE SET
            product_name_platform = EXCLUDED.product_name_platform,
            style_id_normalized = EXCLUDED.style_id_normalized,
            platform_data = EXCLUDED.platform_data,
            embedding = EXCLUDED.embedding,
            embedding_text = EXCLUDED.embedding_text,
            updated_at = CURRENT_TIMESTAMP
    """

    while not stop_event.is_set() or not queue.empty():
        try:
            product = queue.get(timeout=1)
            if product is None:
                break
            cursor.execute(insert_query, (
                product['product_id_platform'], product['platform'], product['platform_id'],
                product['product_name_platform'], product['style_id_platform'],
                product['style_id_normalized'], product['platform_data'],
                product['embedding'], product['embedding_text'], product['keyword_used']
            ))
            conn.commit()
            stats['inserted'] += 1
            if stats['inserted'] % 100 == 0:
                print(f"   💾 Inserted: {stats['inserted']:,} | Generated: {stats['generated']:,} | Failed: {stats['failed']} | Skipped: {stats['skipped']:,}")
            queue.task_done()
        except Exception as e:
            if not stop_event.is_set():
                stats['failed'] += 1
    cursor.close()
    conn.close()

def process_with_queue(products: List[Dict], phase_name: str):
    queue = Queue()
    worker = Thread(target=insert_worker, args=(queue,))
    worker.start()

    print(f"\n🚀 {phase_name}: Processing {len(products):,} products...")

    for i, product in enumerate(products):
        if stop_event.is_set():
            print(f"\n⚠️  Stopped at product {i+1:,}/{len(products):,}")
            break

        embedding_text = product['embedding_text']
        if embedding_text:
            embedding = generate_embedding(embedding_text)
            if embedding:
                product['embedding'] = embedding
                stats['generated'] += 1
                queue.put(product)
            else:
                stats['failed'] += 1
        else:
            stats['skipped'] += 1

    print(f"\n⏳ Waiting for {phase_name} insertions to complete...")
    queue.put(None)
    worker.join()

# ==================== MAIN ====================

def main():
    print("=" * 80)
    print("SUPABASE FULL MIGRATION - ALL PRODUCTS")
    print("=" * 80)
    print("\n💰 Estimated Cost: ~$7.40 (text-embedding-3-small)")
    print("⏱️  Estimated Time: 8-12 hours")
    print("📊 Total Products: ~462,000")
    print("\nPress Ctrl+C anytime to stop gracefully\n")

    # PHASE 1: Inventory
    print("=" * 80)
    print("🎯 PHASE 1: Inventory-Matched Products (PRIORITY)")
    print("=" * 80)
    stockx_inv = fetch_stockx_inventory_subset()
    alias_inv = fetch_alias_inventory_subset()
    print(f"   StockX: {len(stockx_inv):,}")
    print(f"   Alias: {len(alias_inv):,}")

    all_phase1 = []
    for p in stockx_inv:
        all_phase1.append(transform_stockx_product(p))
    for p in alias_inv:
        all_phase1.append(transform_alias_product(p))

    if all_phase1:
        process_with_queue(all_phase1, "Phase 1")

    if stop_event.is_set():
        print("\n❌ Stopped during Phase 1")
        return

    # PHASE 2: StockX with StyleID
    print("\n" + "=" * 80)
    print("📋 PHASE 2: All StockX Products WITH Style IDs")
    print("=" * 80)
    stockx_with_style = fetch_stockx_with_style_id_exclude_migrated()
    print(f"   Remaining: {len(stockx_with_style):,} products")

    all_phase2 = []
    for p in stockx_with_style:
        all_phase2.append(transform_stockx_product(p))

    if all_phase2:
        process_with_queue(all_phase2, "Phase 2")

    if stop_event.is_set():
        print("\n❌ Stopped during Phase 2")
        return

    # PHASE 3: StockX without StyleID + All Alias
    print("\n" + "=" * 80)
    print("📝 PHASE 3: Products WITHOUT Style IDs + All Alias")
    print("=" * 80)
    stockx_no_style = fetch_stockx_without_style_id_exclude_migrated()
    alias_all = fetch_alias_exclude_migrated()
    print(f"   StockX (no styleId): {len(stockx_no_style):,}")
    print(f"   Alias (remaining): {len(alias_all):,}")

    all_phase3 = []
    for p in stockx_no_style:
        all_phase3.append(transform_stockx_product(p))
    for p in alias_all:
        all_phase3.append(transform_alias_product(p))

    if all_phase3:
        process_with_queue(all_phase3, "Phase 3")

    # SUMMARY
    print("\n" + "=" * 80)
    print("✅ MIGRATION COMPLETE!")
    print("=" * 80)
    print(f"   Generated: {stats['generated']:,}")
    print(f"   Inserted: {stats['inserted']:,}")
    print(f"   Failed: {stats['failed']}")
    print(f"   Skipped: {stats['skipped']:,}")

if __name__ == "__main__":
    main()
