"""
Test Similarity Thresholds for Product Mapping
===============================================

Shows sample matches at different similarity thresholds so you can
pick the best threshold to avoid false positives.

Compares:
- Alias product name
- Matched StockX product name
- Similarity score
- Style IDs (if available)
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SUPABASE_CONFIG = {
    'host': os.getenv('SUPABASE_HOST'),
    'database': os.getenv('SUPABASE_DATABASE'),
    'user': os.getenv('SUPABASE_USER'),
    'password': os.getenv('SUPABASE_PASSWORD'),
    'port': int(os.getenv('SUPABASE_PORT', '5432'))
}


def test_threshold(min_similarity, sample_size=50):
    """Test a specific similarity threshold and show sample matches"""

    conn = psycopg2.connect(**SUPABASE_CONFIG)
    cur = conn.cursor()

    # Get random sample of alias products
    cur.execute("""
        SELECT product_id_internal, product_name_platform, style_id_platform, embedding
        FROM products
        WHERE platform = 'alias'
          AND embedding IS NOT NULL
        ORDER BY RANDOM()
        LIMIT %s
    """, (sample_size,))

    alias_products = cur.fetchall()

    matches = []

    for alias_id, alias_name, alias_style, alias_embedding in alias_products:
        # Find best stockx match
        cur.execute("""
            SELECT
                product_id_internal,
                product_name_platform,
                style_id_platform,
                1 - (embedding <=> %s::vector) AS similarity
            FROM products
            WHERE platform = 'stockx'
              AND embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT 1
        """, (alias_embedding,))

        result = cur.fetchone()

        if result:
            stockx_id, stockx_name, stockx_style, similarity = result

            if similarity >= min_similarity:
                matches.append({
                    'alias_name': alias_name,
                    'alias_style': alias_style,
                    'stockx_name': stockx_name,
                    'stockx_style': stockx_style,
                    'similarity': similarity,
                    'style_match': alias_style == stockx_style if alias_style and stockx_style else None
                })

    cur.close()
    conn.close()

    return matches


def display_matches(threshold, matches):
    """Display matches in a readable format"""

    print(f"\n{'='*100}")
    print(f"THRESHOLD: {threshold:.2f} ({threshold*100:.0f}% similarity)")
    print(f"{'='*100}")
    print(f"Matches found: {len(matches)}")

    if not matches:
        print("   No matches at this threshold")
        return

    # Sort by similarity DESC
    matches.sort(key=lambda x: x['similarity'], reverse=True)

    print(f"\n{'Similarity':<12} {'Style Match':<12} {'Alias → StockX':<80}")
    print("-" * 100)

    for m in matches:
        style_match_symbol = '✅' if m['style_match'] else '❌' if m['style_match'] is False else '❓'

        # Truncate long names
        alias_name = m['alias_name'][:35]
        stockx_name = m['stockx_name'][:35]

        print(f"{m['similarity']:.4f}       {style_match_symbol}            {alias_name} → {stockx_name}")

        # Show style IDs if available
        if m['alias_style'] or m['stockx_style']:
            alias_style_display = m['alias_style'] or 'N/A'
            stockx_style_display = m['stockx_style'] or 'N/A'
            print(f"{'':12}                [{alias_style_display}] → [{stockx_style_display}]")
        print()


def analyze_threshold(matches):
    """Analyze match quality at this threshold"""

    if not matches:
        return {
            'total': 0,
            'style_matches': 0,
            'style_mismatches': 0,
            'no_style_id': 0
        }

    style_matches = sum(1 for m in matches if m['style_match'] is True)
    style_mismatches = sum(1 for m in matches if m['style_match'] is False)
    no_style_id = sum(1 for m in matches if m['style_match'] is None)

    return {
        'total': len(matches),
        'style_matches': style_matches,
        'style_mismatches': style_mismatches,
        'no_style_id': no_style_id,
        'style_match_rate': (style_matches / (style_matches + style_mismatches) * 100) if (style_matches + style_mismatches) > 0 else 0
    }


def main():
    print("\n" + "="*100)
    print("SIMILARITY THRESHOLD TESTING")
    print("="*100)
    print("\nTesting different thresholds to find the best balance...")
    print("Lower threshold = more matches, higher risk of false positives")
    print("Higher threshold = fewer matches, more confidence in correctness")

    # Test different thresholds
    thresholds = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70]

    sample_size = 100  # Test with 100 random alias products

    results = {}

    for threshold in thresholds:
        print(f"\n🔍 Testing threshold {threshold:.2f}...")
        matches = test_threshold(threshold, sample_size)
        results[threshold] = {
            'matches': matches,
            'stats': analyze_threshold(matches)
        }

    # Display all results
    for threshold in thresholds:
        display_matches(threshold, results[threshold]['matches'][:10])  # Show top 10 per threshold

    # Summary comparison
    print("\n" + "="*100)
    print("SUMMARY COMPARISON")
    print("="*100)
    print(f"\n{'Threshold':<12} {'Matches':<10} {'Style Match':<15} {'Style Mismatch':<18} {'No Style ID':<15} {'Match Rate':<12}")
    print("-" * 100)

    for threshold in thresholds:
        stats = results[threshold]['stats']
        print(f"{threshold:.2f}        {stats['total']:<10} {stats['style_matches']:<15} {stats['style_mismatches']:<18} {stats['no_style_id']:<15} {stats['style_match_rate']:.1f}%")

    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)
    print("\n✅ Start with 0.90 (90%) threshold:")
    print("   - High confidence in matches")
    print("   - Low false positive risk")
    print("   - You can manually review and lower if needed")
    print("\n⚠️  Avoid thresholds below 0.85 unless you're willing to manually verify")
    print("\n💡 To use a threshold, update create_product_mappings.py:")
    print("   map_by_embedding_similarity(min_similarity=0.90)")
    print("\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
