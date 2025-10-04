"""
Supabase Products Migration Script - Platform Agnostic

Migrates product data from MySQL to Supabase in 3 phases:
1. Inventory-relevant products (PRIORITY)
2. Remaining products WITH style IDs
3. Products WITHOUT style IDs (lowest priority)

Includes exclusion logic to prevent duplicates.

Prerequisites:
- pip install psycopg2-binary pymysql python-dotenv openai
- .env file configured with database credentials
"""

import os
import re
import time
import json
import pymysql
import psycopg2
from typing import List, Dict, Optional
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

# ==================== UTILITY FUNCTIONS ====================

def normalize_style_id(style_id: str) -> Optional[str]:
    """
    Normalize style IDs for matching across platforms.
    Matches the normalize_style_id() SQL function.

    Rules:
    - Remove dashes, spaces, underscores
    - PRESERVE forward slashes (/) for StockX IDs like "W/DM0807-160"
    - Convert to uppercase
    - Remove leading zeros (except standalone '0')
    """
    if not style_id or str(style_id).strip() == '':
        return None

    # Remove dashes, spaces, underscores (preserve forward slashes)
    normalized = str(style_id).replace('-', '').replace(' ', '').replace('_', '')

    # Convert to uppercase
    normalized = normalized.upper()

    # Remove leading zeros (but keep if it's just "0")
    if normalized != '0':
        normalized = normalized.lstrip('0') or '0'

    return normalized if normalized else None


def normalize_text_for_embedding(text: str) -> str:
    """
    Normalize text for embedding creation by compressing underscores and hyphens.
    PRESERVES forward slashes (/) for StockX style IDs.

    Matches the SQL helper functions create_stockx_embedding_text() and create_alias_embedding_text()
    """
    if not text:
        return ""

    # Replace underscores and hyphens with empty string
    # PRESERVE forward slashes (/)
    normalized = text.replace("_", "").replace("-", "")

    return normalized


def generate_embedding_text_stockx(title: str, style_id: Optional[str] = None) -> str:
    """
    Generate embedding text for StockX products.
    Matches create_stockx_embedding_text() SQL function.

    Format: "normalized_style_id normalized_title" or just "normalized_title"
    """
    normalized_title = normalize_text_for_embedding(title) if title else ""

    if style_id:
        normalized_style_id = normalize_text_for_embedding(style_id)
        return f"{normalized_style_id} {normalized_title}".strip()
    else:
        return normalized_title


def generate_embedding_text_alias(name: str, sku: Optional[str] = None) -> str:
    """
    Generate embedding text for Alias products.
    Matches create_alias_embedding_text() SQL function.

    Format: "normalized_name normalized_sku" or just "normalized_name"
    """
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if sku:
        normalized_sku = normalize_text_for_embedding(sku)
        return f"{normalized_name} {normalized_sku}".strip()
    else:
        return normalized_name

def generate_embedding(text: str, retry_count: int = 3) -> Optional[List[float]]:
    """Generate OpenAI embedding for text with retry logic"""
    for attempt in range(retry_count):
        try:
            response = client.embeddings.create(
                input=text,
                model="text-embedding-3-small"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"⚠️  OpenAI API error (attempt {attempt + 1}/{retry_count}): {e}")
            if attempt < retry_count - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"❌ Failed to generate embedding after {retry_count} attempts")
                return None
    return None

# ==================== MYSQL DATA FETCHING ====================

def fetch_stockx_inventory_subset() -> List[Dict]:
    """Fetch StockX products matching inventory (Phase 1 - Priority)"""
    print("📦 Fetching StockX products (Inventory Subset - Priority)...")

    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = """
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
    """

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    print(f"✅ Fetched {len(results)} StockX products (from inventory)")
    return results

def fetch_alias_inventory_subset() -> List[Dict]:
    """Fetch Alias products matching inventory (Phase 1 - Priority)"""
    print("📦 Fetching Alias products (Inventory Subset - Priority)...")

    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = """
        SELECT DISTINCT ap.*
        FROM alias_products ap
        JOIN (
            SELECT
                item,
                REPLACE(
                    SUBSTRING_INDEX(SUBSTRING_INDEX(item, '[', -1), ']', 1),
                    '-', ' '
                ) AS extracted_styleId
            FROM inventory
            WHERE item LIKE '%[%]%'
        ) i
        ON ap.sku = i.extracted_styleId
    """

    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    print(f"✅ Fetched {len(results)} Alias products (from inventory)")
    return results

def fetch_stockx_with_style_id_exclude_migrated() -> List[Dict]:
    """Fetch remaining StockX products WITH style IDs (Phase 2)
    EXCLUDES products already migrated in Phase 1"""
    print("📦 Fetching StockX products WITH style IDs (excluding already migrated)...")

    conn_mysql = pymysql.connect(**MYSQL_CONFIG)
    conn_pg = psycopg2.connect(**SUPABASE_CONFIG)

    cursor_mysql = conn_mysql.cursor(pymysql.cursors.DictCursor)
    cursor_pg = conn_pg.cursor()

    # Get already migrated StockX product IDs
    cursor_pg.execute("""
        SELECT product_id_platform FROM products WHERE platform = 'stockx'
    """)
    migrated_ids = {row[0] for row in cursor_pg.fetchall()}

    # Fetch StockX products with style IDs, excluding migrated ones
    cursor_mysql.execute("""
        SELECT *
        FROM stockx_products
        WHERE styleId IS NOT NULL
          AND styleId != ''
    """)
    results = cursor_mysql.fetchall()

    # Filter out already migrated
    results = [r for r in results if r['productId'] not in migrated_ids]

    cursor_mysql.close()
    cursor_pg.close()
    conn_mysql.close()
    conn_pg.close()

    print(f"✅ Fetched {len(results)} StockX products (with style_id, excluding migrated)")
    return results

def fetch_stockx_without_style_id_exclude_migrated() -> List[Dict]:
    """Fetch StockX products WITHOUT style IDs (Phase 3)
    EXCLUDES products already migrated"""
    print("📦 Fetching StockX products WITHOUT style IDs (excluding already migrated)...")

    conn_mysql = pymysql.connect(**MYSQL_CONFIG)
    conn_pg = psycopg2.connect(**SUPABASE_CONFIG)

    cursor_mysql = conn_mysql.cursor(pymysql.cursors.DictCursor)
    cursor_pg = conn_pg.cursor()

    # Get already migrated StockX product IDs
    cursor_pg.execute("""
        SELECT product_id_platform FROM products WHERE platform = 'stockx'
    """)
    migrated_ids = {row[0] for row in cursor_pg.fetchall()}

    # Fetch StockX products without style IDs, excluding migrated ones
    cursor_mysql.execute("""
        SELECT *
        FROM stockx_products
        WHERE styleId IS NULL
           OR styleId = ''
    """)
    results = cursor_mysql.fetchall()

    # Filter out already migrated
    results = [r for r in results if r['productId'] not in migrated_ids]

    cursor_mysql.close()
    cursor_pg.close()
    conn_mysql.close()
    conn_pg.close()

    print(f"✅ Fetched {len(results)} StockX products (without style_id, excluding migrated)")
    return results

def fetch_alias_exclude_migrated() -> List[Dict]:
    """Fetch remaining Alias products (Phase 3)
    EXCLUDES products already migrated"""
    print("📦 Fetching Alias products (excluding already migrated)...")

    conn_mysql = pymysql.connect(**MYSQL_CONFIG)
    conn_pg = psycopg2.connect(**SUPABASE_CONFIG)

    cursor_mysql = conn_mysql.cursor(pymysql.cursors.DictCursor)
    cursor_pg = conn_pg.cursor()

    # Get already migrated Alias product IDs
    cursor_pg.execute("""
        SELECT product_id_platform FROM products WHERE platform = 'alias'
    """)
    migrated_ids = {row[0] for row in cursor_pg.fetchall()}

    # Fetch Alias products, excluding migrated ones
    cursor_mysql.execute("""
        SELECT *
        FROM alias_products
    """)
    results = cursor_mysql.fetchall()

    # Filter out already migrated
    results = [r for r in results if r['catalogId'] not in migrated_ids]

    cursor_mysql.close()
    cursor_pg.close()
    conn_mysql.close()
    conn_pg.close()

    print(f"✅ Fetched {len(results)} Alias products (excluding migrated)")
    return results

# ==================== DATA TRANSFORMATION ====================

def transform_stockx_product(product: Dict) -> Dict:
    """Transform StockX product to platform-agnostic schema"""
    style_id = product.get('styleId')
    product_name = product.get('title', '')

    # Build platform_data JSON with all StockX-specific fields
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
    """Transform Alias product to platform-agnostic schema"""
    product_name = product.get('name', '')
    sku = product.get('sku')

    # Build platform_data JSON with all Alias-specific fields
    platform_data = {
        'sku': sku,
        'gender': product.get('gender')
    }

    return {
        'product_id_platform': product.get('catalogId'),
        'platform': 'alias',
        'platform_id': None,
        'product_name_platform': product_name,
        'style_id_platform': None,  # Alias doesn't provide style IDs
        'style_id_normalized': None,
        'platform_data': json.dumps(platform_data),
        'keyword_used': product.get('keywordUsed'),
        'embedding': None,
        'embedding_text': generate_embedding_text_alias(product_name, sku)
    }

# ==================== EMBEDDING GENERATION ====================

def generate_embeddings_batch(products: List[Dict], batch_size: int = 50):
    """Generate embeddings for all products in batches"""
    print(f"🤖 Generating embeddings for {len(products)} products...")

    total = len(products)
    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"   Processing batch {batch_num}/{total_batches} ({len(batch)} products)...")

        for product in batch:
            embedding_text = product['embedding_text']
            if embedding_text:
                embedding = generate_embedding(embedding_text)
                product['embedding'] = embedding
                if not embedding:
                    print(f"      ⚠️  Failed: {product['product_name_platform']}")

        if i + batch_size < total:
            time.sleep(1)

    success_count = sum(1 for p in products if p['embedding'] is not None)
    print(f"✅ Generated {success_count}/{total} embeddings successfully")

# ==================== SUPABASE INSERTION ====================

def insert_to_supabase(products: List[Dict], batch_size: int = 100):
    """Insert products into Supabase in batches"""
    print(f"💾 Inserting {len(products)} products into Supabase...")

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cursor = conn.cursor()

    insert_query = """
        INSERT INTO products (
            product_id_platform, platform, platform_id,
            product_name_platform, style_id_platform, style_id_normalized,
            platform_data,
            embedding, embedding_text,
            keyword_used
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s,
            %s::jsonb,
            %s, %s,
            %s
        )
        ON CONFLICT (product_id_platform)
        DO UPDATE SET
            product_name_platform = EXCLUDED.product_name_platform,
            style_id_normalized = EXCLUDED.style_id_normalized,
            platform_data = EXCLUDED.platform_data,
            embedding = EXCLUDED.embedding,
            embedding_text = EXCLUDED.embedding_text,
            updated_at = CURRENT_TIMESTAMP
    """

    total = len(products)
    inserted_count = 0
    error_count = 0

    for i in range(0, total, batch_size):
        batch = products[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"   Inserting batch {batch_num}/{total_batches} ({len(batch)} products)...")

        for product in batch:
            try:
                cursor.execute(insert_query, (
                    product['product_id_platform'],
                    product['platform'],
                    product['platform_id'],
                    product['product_name_platform'],
                    product['style_id_platform'],
                    product['style_id_normalized'],
                    product['platform_data'],
                    product['embedding'],
                    product['embedding_text'],
                    product['keyword_used']
                ))
                inserted_count += 1
            except Exception as e:
                error_count += 1
                print(f"      ❌ Error: {product['product_name_platform']}: {e}")

        conn.commit()

    cursor.close()
    conn.close()

    print(f"✅ Inserted {inserted_count}/{total} products successfully")
    if error_count > 0:
        print(f"⚠️  {error_count} products failed to insert")

# ==================== MAIN EXECUTION ====================

def main():
    """Main migration execution"""
    print("=" * 60)
    print("SUPABASE PRODUCTS MIGRATION - PLATFORM AGNOSTIC")
    print("=" * 60)
    print()

    all_products = []

    # ==================== PHASE 1: Inventory-Relevant (PRIORITY) ====================
    print("🎯 PHASE 1: Inventory-relevant products (PRIORITY)")
    print("-" * 60)

    stockx_inventory = fetch_stockx_inventory_subset()
    alias_inventory = fetch_alias_inventory_subset()

    print(f"   Phase 1 Total: {len(stockx_inventory) + len(alias_inventory)} products")
    print()

    for product in stockx_inventory:
        all_products.append(transform_stockx_product(product))
    for product in alias_inventory:
        all_products.append(transform_alias_product(product))

    # ==================== PHASE 2: WITH Style IDs ====================
    print("📋 PHASE 2: Remaining products WITH style IDs")
    print("-" * 60)

    # Uncomment when ready
    # stockx_with_style = fetch_stockx_with_style_id_exclude_migrated()
    # print(f"   Phase 2 StockX: {len(stockx_with_style)} products")
    # for product in stockx_with_style:
    #     all_products.append(transform_stockx_product(product))

    print("   ⏭️  Skipped Phase 2 (uncomment to enable)")
    print()

    # ==================== PHASE 3: WITHOUT Style IDs ====================
    print("📝 PHASE 3: Products WITHOUT style IDs (lower priority)")
    print("-" * 60)

    # Uncomment when ready
    # stockx_no_style = fetch_stockx_without_style_id_exclude_migrated()
    # alias_remaining = fetch_alias_exclude_migrated()
    # print(f"   Phase 3 Total: {len(stockx_no_style) + len(alias_remaining)} products")
    # for product in stockx_no_style:
    #     all_products.append(transform_stockx_product(product))
    # for product in alias_remaining:
    #     all_products.append(transform_alias_product(product))

    print("   ⏭️  Skipped Phase 3 (uncomment to enable)")
    print()

    # ==================== PROCESS & INSERT ====================
    print("=" * 60)
    print(f"Total products to process: {len(all_products)}")
    print("=" * 60)
    print()

    if len(all_products) == 0:
        print("⚠️  No products to migrate. Exiting.")
        return

    generate_embeddings_batch(all_products)
    insert_to_supabase(all_products)

    print("=" * 60)
    print("✅ MIGRATION COMPLETE!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  • Total migrated: {len(all_products)}")
    print(f"  • StockX: {sum(1 for p in all_products if p['platform'] == 'stockx')}")
    print(f"  • Alias: {sum(1 for p in all_products if p['platform'] == 'alias')}")
    print()
    print("Next steps:")
    print("1. Run sql/03_verify.sql")
    print("2. Uncomment Phase 2 & 3 when ready")
    print("3. Update application code")

if __name__ == "__main__":
    main()
