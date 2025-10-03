"""
Supabase Products Migration Script V2 - With Async Queue & Safe Stop

Features:
- Async insertion queue - inserts products as embeddings are generated
- Safe stop mechanism - press Ctrl+C to gracefully stop
- Real-time progress tracking
"""

import os
import time
import json
import pymysql
import psycopg2
import asyncio
import signal
import sys
from typing import List, Dict, Optional
from queue import Queue
from threading import Thread, Event
from dotenv import load_dotenv
import openai

# Load environment variables
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
    'port': 5432
}

# OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Global stop event
stop_event = Event()
stats = {'generated': 0, 'inserted': 0, 'failed': 0}

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n⚠️  Stopping gracefully... (Ctrl+C again to force quit)")
    stop_event.set()

signal.signal(signal.SIGINT, signal_handler)

# ==================== UTILITY FUNCTIONS (same as before) ====================

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
    """Generate OpenAI embedding for text"""
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

# ==================== MYSQL DATA FETCHING ====================

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
    cursor.close()
    conn.close()
    return results

# ==================== DATA TRANSFORMATION ====================

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

# ==================== ASYNC INSERTION QUEUE ====================

def insert_worker(queue: Queue):
    """Worker thread that inserts products from queue"""
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
            if product is None:  # Poison pill
                break

            cursor.execute(insert_query, (
                product['product_id_platform'], product['platform'], product['platform_id'],
                product['product_name_platform'], product['style_id_platform'],
                product['style_id_normalized'], product['platform_data'],
                product['embedding'], product['embedding_text'], product['keyword_used']
            ))
            conn.commit()
            stats['inserted'] += 1

            # Print progress every 10 inserts
            if stats['inserted'] % 10 == 0:
                print(f"   💾 Inserted: {stats['inserted']} | Generated: {stats['generated']} | Failed: {stats['failed']}")

            queue.task_done()
        except Exception as e:
            if not stop_event.is_set():
                stats['failed'] += 1
                continue

    cursor.close()
    conn.close()

def process_with_queue(products: List[Dict]):
    """Process products with async insertion queue"""
    queue = Queue()

    # Start insert worker thread
    worker = Thread(target=insert_worker, args=(queue,))
    worker.start()

    print(f"\n🚀 Processing {len(products)} products with async queue...")
    print("   Press Ctrl+C to stop gracefully\n")

    for i, product in enumerate(products):
        if stop_event.is_set():
            print(f"\n⚠️  Stopped at product {i+1}/{len(products)}")
            break

        # Generate embedding
        embedding_text = product['embedding_text']
        if embedding_text:
            embedding = generate_embedding(embedding_text)
            if embedding:
                product['embedding'] = embedding
                stats['generated'] += 1
                queue.put(product)  # Add to insertion queue
            else:
                stats['failed'] += 1

    # Wait for queue to empty
    print("\n⏳ Waiting for all insertions to complete...")
    queue.put(None)  # Poison pill
    worker.join()

    print(f"\n✅ Complete!")
    print(f"   Generated: {stats['generated']}")
    print(f"   Inserted: {stats['inserted']}")
    print(f"   Failed: {stats['failed']}")

# ==================== MAIN ====================

def main():
    print("=" * 60)
    print("SUPABASE MIGRATION V2 - With Async Queue & Safe Stop")
    print("=" * 60)

    print("\n📦 Fetching products from MySQL...")
    stockx_inventory = fetch_stockx_inventory_subset()
    alias_inventory = fetch_alias_inventory_subset()

    print(f"   StockX: {len(stockx_inventory)}")
    print(f"   Alias: {len(alias_inventory)}")

    all_products = []
    for p in stockx_inventory:
        all_products.append(transform_stockx_product(p))
    for p in alias_inventory:
        all_products.append(transform_alias_product(p))

    if not all_products:
        print("⚠️  No products to migrate")
        return

    process_with_queue(all_products)

if __name__ == "__main__":
    main()
