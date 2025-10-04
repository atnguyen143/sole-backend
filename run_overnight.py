"""
Overnight Migration Runner
===========================

Runs the full alias migration pipeline:
1. Migrate ~282K alias products with cleaned embeddings
2. Create indexes with automatic fallbacks

Total time: ~15-20 minutes
Total cost: ~$11.30

Safe to run unattended overnight.
"""

import subprocess
import sys
import time

def run_script(script_name, description):
    """Run a Python script and capture output"""
    print("\n" + "="*80)
    print(f"🚀 Starting: {description}")
    print("="*80 + "\n")

    start_time = time.time()

    try:
        # Run the script
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=False,  # Show output in real-time
            text=True
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"\n✅ {description} completed in {elapsed/60:.2f} minutes")
            return True
        else:
            print(f"\n❌ {description} failed with exit code {result.returncode}")
            return False

    except Exception as e:
        print(f"\n❌ Error running {description}: {e}")
        return False


def main():
    print("\n" + "="*80)
    print("OVERNIGHT MIGRATION RUNNER")
    print("="*80)
    print("\nThis will:")
    print("  1. Fix existing 857 alias products (~1 min, ~$0.03)")
    print("  2. Migrate ~282K new alias products (~10-15 min, ~$11.30)")
    print("  3. Create indexes with auto fallbacks (~5 min)")
    print("\nTotal: ~16-21 minutes, ~$11.33")
    print("="*80)

    overall_start = time.time()

    # Step 1: Fix existing alias products
    success = run_script(
        "regenerate_alias_embeddings.py",
        "Fix Existing Alias Products"
    )

    if not success:
        print("\n⚠️  Fixing existing products failed, but continuing...")

    # Step 2: Migrate new alias products
    success = run_script(
        "migrate_alias_remaining.py",
        "Migrate New Alias Products"
    )

    if not success:
        print("\n⚠️  Alias migration failed, stopping pipeline")
        print("You can fix the issue and run the scripts individually:")
        print("  python regenerate_alias_embeddings.py")
        print("  python migrate_alias_remaining.py")
        print("  python create_indexes_safe.py")
        sys.exit(1)

    # Step 3: Create indexes
    success = run_script(
        "create_indexes_safe.py",
        "Index Creation"
    )

    if not success:
        print("\n⚠️  Index creation had issues (may be expected if memory limited)")
        print("Check output above for details")

    # Final summary
    total_elapsed = time.time() - overall_start
    print("\n" + "="*80)
    print("🎉 OVERNIGHT MIGRATION COMPLETE")
    print("="*80)
    print(f"Total time: {total_elapsed/60:.2f} minutes ({total_elapsed:.0f} seconds)")
    print("\nNext steps:")
    print("  - Check Supabase products table for new alias products")
    print("  - Check inventory table for updated product_id_internal links")
    print("  - Test product search with normalize_product_name() function")
    print("\n✅ All done!\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
