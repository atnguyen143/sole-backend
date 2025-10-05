"""
INSERT ALL PRODUCTS - NO EMBEDDINGS
====================================

Fast insert of all products from MySQL → Supabase WITHOUT embeddings
This is MUCH faster since we skip the OpenAI API calls

Steps:
1. Insert all StockX products (NO embeddings)
2. Insert all Alias products (NO embeddings)

Speed: ~2-5 minutes for 461K products
Cost: $0 (no API calls)
"""

import os
import re
import time
import pymysql
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# Configuration
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

BATCH_SIZE = 1000  # Even bigger batches since no API calls


def retry_db_operation(func, max_retries=3, *args, **kwargs):
    """Retry database operations with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"   ⚠️  DB error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"   ⏳ Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise
    return None


def normalize_text_for_embedding(text):
    """Normalize text for embeddings (original case preserved)"""
    if not text:
        return ""

    # Expand abbreviations first (before removing parentheses)
    text = re.sub(r'\bWmns\b', 'Women', text, flags=re.IGNORECASE)
    text = re.sub(r'\(W\)', 'Women', text, flags=re.IGNORECASE)

    # Remove parentheses, single quotes, hyphens, underscores
    text = text.replace('(', '').replace(')', '').replace("'", '').replace('-', ' ').replace('_', ' ')

    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def generate_embedding_text(name, style_id=None):
    """
    Generate embedding text with delimiter (works for both StockX and Alias)
    Format: "{normalized_style} | {name}" (pipe delimiter separates style from name)

    Examples:
    - style_id="DD0385-100", name="Air Max 90 'Cork'" → "DD0385100 | Air Max 90 Cork"
    - style_id="DD0385-100/DD0385-200", name="Air Max 90" → "DD0385100 DD0385200 | Air Max 90"
    - No style_id, name="Air Max 90" → "Air Max 90"
    """
    normalized_name = normalize_text_for_embedding(name) if name else ""

    if style_id:
        # Remove spaces, dashes, underscores first
        normalized_style = style_id.replace(' ', '').replace('-', '').replace('_', '')
        # THEN replace slashes with spaces (for multi-SKU products)
        normalized_style = normalized_style.replace('/', ' ').upper()
        return f"{normalized_style} | {normalized_name}".strip()

    return normalized_name


# Aliases for backward compatibility
def generate_embedding_text_stockx(name, style_id=None):
    """Generate embedding text for StockX products"""
    return generate_embedding_text(name, style_id)


def generate_embedding_text_alias(name, sku=None):
    """Generate embedding text for alias products"""
    return generate_embedding_text(name, sku)


def normalize_style_id(style_id):
    """Normalize style ID for storage"""
    if not style_id or str(style_id).strip() == '':
        return None

    normalized = str(style_id).replace('-', '').replace(' ', '').replace('_', '').upper()

    if normalized != '0':
        normalized = normalized.lstrip('0') or '0'

    return normalized if normalized else None


def insert_stockx():
    """Insert all StockX products"""
    print("\n" + "="*80)
    print("INSERTING STOCKX PRODUCTS")
    print("="*80 + "\n")

    # Fetch from MySQL
    print("📦 Fetching from MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute("SELECT productId, title, styleId FROM stockx_products")
    products = mysql_cur.fetchall()
    mysql_cur.close()
    mysql_conn.close()

    total = len(products)
    print(f"   ✅ Found {total:,} products\n")

    # Insert to Supabase
    print("💾 Inserting to Supabase...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for batch_start in range(0, total, BATCH_SIZE):
        batch = products[batch_start:batch_start + BATCH_SIZE]

        values_list = []
        for p in batch:
            embedding_text = generate_embedding_text_stockx(p['title'], p['styleId'])
            values_list.append((
                p['productId'],
                'stockx',
                (p['title'] or '').upper(),
                p['styleId'],
                normalize_style_id(p['styleId']),
                embedding_text,
                None  # NO embedding
            ))

        # Retry DB operation with exponential backoff
        def insert_batch():
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO products (
                    product_id_platform,
                    platform,
                    product_name_platform,
                    style_id_platform,
                    style_id_normalized,
                    embedding_text,
                    embedding
                ) VALUES %s
                ON CONFLICT (product_id_platform, platform)
                DO UPDATE SET
                    embedding_text = EXCLUDED.embedding_text,
                    embedding = NULL
                """,
                values_list,
                template="(%s, %s, %s, %s, %s, %s, %s::vector)"
            )
            conn.commit()

        retry_db_operation(insert_batch)

        inserted += len(batch)
        print(f"   {inserted:,}/{total:,} ({inserted/total*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n✅ Inserted {inserted:,} StockX products\n")
    return inserted


def insert_alias():
    """Insert all Alias products"""
    print("\n" + "="*80)
    print("INSERTING ALIAS PRODUCTS")
    print("="*80 + "\n")

    # Fetch from MySQL
    print("📦 Fetching from MySQL...")
    mysql_conn = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    mysql_cur = mysql_conn.cursor()
    mysql_cur.execute("SELECT catalogId, name, sku, keywordUsed FROM alias_products")
    products = mysql_cur.fetchall()
    mysql_cur.close()
    mysql_conn.close()

    total = len(products)
    print(f"   ✅ Found {total:,} products\n")

    # Insert to Supabase
    print("💾 Inserting to Supabase...")
    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for batch_start in range(0, total, BATCH_SIZE):
        batch = products[batch_start:batch_start + BATCH_SIZE]

        values_list = []
        for p in batch:
            embedding_text = generate_embedding_text_alias(p['name'], p['sku'])
            values_list.append((
                p['catalogId'],
                'alias',
                (p['name'] or '').upper(),
                p['sku'],
                normalize_style_id(p['sku']),
                embedding_text,
                None,  # NO embedding
                p.get('keywordUsed')
            ))

        # Retry DB operation with exponential backoff
        def insert_batch():
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO products (
                    product_id_platform,
                    platform,
                    product_name_platform,
                    style_id_platform,
                    style_id_normalized,
                    embedding_text,
                    embedding,
                    keyword_used
                ) VALUES %s
                ON CONFLICT (product_id_platform, platform)
                DO UPDATE SET
                    embedding_text = EXCLUDED.embedding_text,
                    embedding = NULL
                """,
                values_list,
                template="(%s, %s, %s, %s, %s, %s, %s::vector, %s)"
            )
            conn.commit()

        retry_db_operation(insert_batch)

        inserted += len(batch)
        print(f"   {inserted:,}/{total:,} ({inserted/total*100:.1f}%)")

    cur.close()
    conn.close()

    print(f"\n✅ Inserted {inserted:,} Alias products\n")
    return inserted


def main():
    print("\n" + "="*80)
    print("INSERT ALL PRODUCTS - NO EMBEDDINGS")
    print("="*80)
    print("\nThis will insert all products WITHOUT embeddings")
    print("Speed: 2-5 minutes")
    print("Cost: $0")
    print("\n" + "="*80 + "\n")

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("❌ Cancelled")
        return

    import time
    start = time.time()

    stockx_count = insert_stockx()
    alias_count = insert_alias()

    elapsed = time.time() - start

    print("\n" + "="*80)
    print("COMPLETE")
    print("="*80)
    print(f"✅ StockX: {stockx_count:,}")
    print(f"✅ Alias:  {alias_count:,}")
    print(f"⏱️  Time:  {elapsed/60:.2f} minutes")
    print(f"⚡ Rate:  {(stockx_count + alias_count)/elapsed:.0f} products/sec")
    print("\n💡 Next: Generate embeddings or create index\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
