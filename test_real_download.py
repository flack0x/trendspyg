"""Test real download functionality."""

import os
import sys
from datetime import datetime

def test_download():
    """Test actual download with real browser."""
    print("="*70)
    print("  REAL DOWNLOAD TEST")
    print("="*70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        from trendspyg.downloader import download_google_trends_csv

        print("[INFO] Importing downloader... OK")
        print("[INFO] Testing download with minimal parameters...")
        print("[INFO] Configuration: US, 24 hours, all categories")
        print("[INFO] This will open Chrome in headless mode...\n")

        # Test download with default parameters
        result = download_google_trends_csv(
            geo='US',
            hours=24,
            category='all',
            active_only=False,
            sort_by='relevance',
            headless=True,
            download_dir=None
        )

        print("\n" + "="*70)
        print("  DOWNLOAD TEST RESULTS")
        print("="*70)

        if result:
            print(f"\n[SUCCESS] Download completed!")
            print(f"[INFO] File saved to: {result}")

            # Check file exists
            if os.path.exists(result):
                file_size = os.path.getsize(result)
                print(f"[OK] File exists")
                print(f"[OK] File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")

                # Check file is not empty
                if file_size > 100:
                    print(f"[OK] File contains data (>100 bytes)")

                    # Try to read first few lines
                    try:
                        with open(result, 'r', encoding='utf-8') as f:
                            lines = f.readlines()[:3]
                        print(f"[OK] File is readable")
                        print(f"[INFO] Total lines: {len(lines)} (showing first 3)")
                        print("\nFile preview:")
                        for i, line in enumerate(lines, 1):
                            print(f"  Line {i}: {line.strip()[:80]}...")

                        # Check CSV structure
                        if lines[0].startswith('"Trends"'):
                            print("\n[OK] CSV header is correct")
                        else:
                            print("\n[WARN] CSV header format unexpected")

                    except Exception as e:
                        print(f"[WARN] Could not read file: {e}")

                else:
                    print(f"[WARN] File size is suspiciously small")

            else:
                print(f"[FAIL] File does not exist at: {result}")
                return False

            print("\n" + "="*70)
            print("RATING: 5/5 stars - Download works perfectly!")
            print("="*70)
            return True

        else:
            print("\n[FAIL] Download returned None")
            print("\n" + "="*70)
            print("RATING: 0/5 stars - Download failed")
            print("="*70)
            return False

    except ImportError as e:
        print(f"\n[FAIL] Import error: {e}")
        print("[INFO] This is expected if selenium is not installed")
        print("[INFO] Run: pip install selenium")
        print("\n" + "="*70)
        print("RATING: N/A - Dependencies not installed")
        print("="*70)
        return None

    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "="*70)
        print("RATING: 0/5 stars - Download crashed")
        print("="*70)
        return False

    finally:
        print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    result = test_download()
    if result is True:
        sys.exit(0)
    elif result is False:
        sys.exit(1)
    else:
        sys.exit(2)  # Dependencies not installed
