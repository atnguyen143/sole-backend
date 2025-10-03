"""
Product Search using Vector Embeddings
Finds matching Alias and StockX products based on semantic similarity
"""

import os
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_HOST = os.getenv("SUPABASE_HOST")
SUPABASE_DATABASE = os.getenv("SUPABASE_DATABASE", "postgres")
SUPABASE_USER = os.getenv("SUPABASE_USER")
SUPABASE_PASSWORD = os.getenv("SUPABASE_PASSWORD")
SUPABASE_PORT = os.getenv("SUPABASE_PORT", "5432")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


def get_supabase_connection():
    """Create Supabase connection"""
    conn_string = f"postgresql://{SUPABASE_USER}:{SUPABASE_PASSWORD}@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DATABASE}"
    return psycopg2.connect(conn_string)


def create_query_embedding(query_text):
    """Generate embedding for search query"""
    try:
        response = client.embeddings.create(
            input=query_text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error creating embedding: {e}")
        return None


def search_products(query, limit=10, platform_filter=None, min_similarity=0.7):
    """
    Search for products using vector similarity

    Args:
        query: Search query string (e.g., "metallic reimagined")
        limit: Number of results to return (default 10)
        platform_filter: Filter by platform ("alias" or "stockx"), None for both
        min_similarity: Minimum cosine similarity score (0-1, default 0.7)

    Returns:
        List of matching products with their details
    """
    print(f"\n🔍 Searching for: '{query}'")
    print(f"   Platform filter: {platform_filter or 'All'}")
    print(f"   Min similarity: {min_similarity}")
    print(f"   Results limit: {limit}\n")

    # Create embedding for query
    query_embedding = create_query_embedding(query)
    if not query_embedding:
        print("❌ Failed to create query embedding")
        return []

    # Connect to Supabase
    conn = get_supabase_connection()
    cursor = conn.cursor()

    try:
        # Build SQL query with optional platform filter
        platform_condition = ""
        params = [query_embedding, query_embedding, min_similarity]

        if platform_filter:
            platform_condition = "AND platform = %s"
            params.append(platform_filter)

        params.append(limit)

        sql = f"""
        SELECT
            product_id_platform,
            platform,
            product_name_platform,
            style_id_platform,
            style_id_normalized,
            embedding_text,
            keyword_used,
            1 - (embedding <=> %s::vector) AS similarity
        FROM products
        WHERE embedding IS NOT NULL
          AND 1 - (embedding <=> %s::vector) >= %s
          {platform_condition}
        ORDER BY similarity DESC
        LIMIT %s
        """

        cursor.execute(sql, params)
        results = cursor.fetchall()

        # Format results
        products = []
        for row in results:
            product = {
                "product_id_platform": row[0],
                "platform": row[1],
                "product_name_platform": row[2],
                "style_id_platform": row[3],
                "style_id_normalized": row[4],
                "embedding_text": row[5],
                "keyword_used": row[6],
                "similarity": round(row[7], 4)
            }
            products.append(product)

        return products

    except Exception as e:
        print(f"❌ Search error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def search_alias_and_stockx(query, limit_per_platform=5, min_similarity=0.7):
    """
    Search for matching products on both Alias and StockX
    Returns separate lists for each platform

    Args:
        query: Search query string
        limit_per_platform: Number of results per platform (default 5)
        min_similarity: Minimum similarity threshold (default 0.7)

    Returns:
        dict with 'alias' and 'stockx' keys containing product lists
    """
    alias_results = search_products(
        query,
        limit=limit_per_platform,
        platform_filter="alias",
        min_similarity=min_similarity
    )

    stockx_results = search_products(
        query,
        limit=limit_per_platform,
        platform_filter="stockx",
        min_similarity=min_similarity
    )

    return {
        "alias": alias_results,
        "stockx": stockx_results
    }


def print_search_results(results):
    """Pretty print search results"""
    if isinstance(results, dict) and "alias" in results:
        # Results from search_alias_and_stockx
        print("\n" + "="*80)
        print("🔵 ALIAS RESULTS")
        print("="*80)
        if results["alias"]:
            for i, product in enumerate(results["alias"], 1):
                print(f"\n{i}. {product['product_name_platform']}")
                print(f"   product_id_platform: {product['product_id_platform']}")
                print(f"   style_id_platform: {product['style_id_platform'] or 'N/A'}")
                print(f"   Similarity: {product['similarity']:.2%}")
                if product['keyword_used']:
                    print(f"   keyword_used: {product['keyword_used']}")
        else:
            print("   No results found")

        print("\n" + "="*80)
        print("🟠 STOCKX RESULTS")
        print("="*80)
        if results["stockx"]:
            for i, product in enumerate(results["stockx"], 1):
                print(f"\n{i}. {product['product_name_platform']}")
                print(f"   product_id_platform: {product['product_id_platform']}")
                print(f"   style_id_platform: {product['style_id_platform'] or 'N/A'}")
                print(f"   Similarity: {product['similarity']:.2%}")
                if product['keyword_used']:
                    print(f"   keyword_used: {product['keyword_used']}")
        else:
            print("   No results found")
    else:
        # Results from search_products
        print("\n" + "="*80)
        print("SEARCH RESULTS")
        print("="*80)
        if results:
            for i, product in enumerate(results, 1):
                print(f"\n{i}. [{product['platform'].upper()}] {product['product_name_platform']}")
                print(f"   product_id_platform: {product['product_id_platform']}")
                print(f"   style_id_platform: {product['style_id_platform'] or 'N/A'}")
                print(f"   Similarity: {product['similarity']:.2%}")
                if product['keyword_used']:
                    print(f"   keyword_used: {product['keyword_used']}")
        else:
            print("   No results found")

    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    # Example: Search for "metallic reimagined" on both platforms
    print("\n🚀 Product Search Demo\n")

    query = "metallic reimagined"
    results = search_alias_and_stockx(query, limit_per_platform=5, min_similarity=0.6)
    print_search_results(results)

    # Example: Get product IDs for bot commands
    if results["alias"] or results["stockx"]:
        print("\n📋 Product IDs for bot commands:")
        if results["alias"]:
            print(f"\nAlias Product ID: {results['alias'][0]['product_id_platform']}")
        if results["stockx"]:
            print(f"StockX Product ID: {results['stockx'][0]['product_id_platform']}")
