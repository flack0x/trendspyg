#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for output format functionality.
Tests CSV, JSON, Parquet, and DataFrame output formats.
"""

import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from trendspyg.downloader import download_google_trends_csv

def test_csv_format():
    """Test CSV format (default)."""
    print("\n" + "="*70)
    print("TEST 1: CSV Format")
    print("="*70)

    try:
        result = download_google_trends_csv(
            geo='US',
            hours=4,
            category='technology',
            headless=True,
            output_format='csv'
        )

        if result and os.path.exists(result):
            print(f"✅ CSV test PASSED: {result}")
            print(f"   File size: {os.path.getsize(result):,} bytes")
            return True
        else:
            print("❌ CSV test FAILED: No file created")
            return False
    except Exception as e:
        print(f"❌ CSV test FAILED: {e}")
        return False


def test_json_format():
    """Test JSON format."""
    print("\n" + "="*70)
    print("TEST 2: JSON Format")
    print("="*70)

    try:
        result = download_google_trends_csv(
            geo='US',
            hours=4,
            category='sports',
            headless=True,
            output_format='json'
        )

        if result and os.path.exists(result):
            print(f"✅ JSON test PASSED: {result}")
            print(f"   File size: {os.path.getsize(result):,} bytes")

            # Verify it's valid JSON
            import json
            with open(result, 'r') as f:
                data = json.load(f)
            print(f"   Records: {len(data)}")
            return True
        else:
            print("❌ JSON test FAILED: No file created")
            return False
    except Exception as e:
        print(f"❌ JSON test FAILED: {e}")
        return False


def test_parquet_format():
    """Test Parquet format."""
    print("\n" + "="*70)
    print("TEST 3: Parquet Format")
    print("="*70)

    try:
        result = download_google_trends_csv(
            geo='US',
            hours=4,
            category='business',
            headless=True,
            output_format='parquet'
        )

        if result and os.path.exists(result):
            print(f"✅ Parquet test PASSED: {result}")
            print(f"   File size: {os.path.getsize(result):,} bytes")

            # Verify it's readable
            import pandas as pd
            df = pd.read_parquet(result)
            print(f"   Rows: {len(df)}, Columns: {len(df.columns)}")
            return True
        else:
            print("❌ Parquet test FAILED: No file created")
            return False
    except Exception as e:
        print(f"❌ Parquet test FAILED: {e}")
        return False


def test_dataframe_format():
    """Test DataFrame format."""
    print("\n" + "="*70)
    print("TEST 4: DataFrame Format")
    print("="*70)

    try:
        result = download_google_trends_csv(
            geo='US',
            hours=4,
            category='entertainment',
            headless=True,
            output_format='dataframe'
        )

        if result is not None:
            import pandas as pd
            if isinstance(result, pd.DataFrame):
                print(f"✅ DataFrame test PASSED")
                print(f"   Shape: {result.shape} (rows, columns)")
                print(f"   Columns: {list(result.columns)}")
                print(f"   Memory usage: ~{result.memory_usage(deep=True).sum():,} bytes")
                return True
            else:
                print(f"❌ DataFrame test FAILED: Result is not a DataFrame (type: {type(result)})")
                return False
        else:
            print("❌ DataFrame test FAILED: Result is None")
            return False
    except Exception as e:
        print(f"❌ DataFrame test FAILED: {e}")
        return False


def main():
    """Run all tests."""
    print("="*70)
    print("TRENDSPYG OUTPUT FORMAT TESTS")
    print("="*70)
    print("Testing all 4 output formats: CSV, JSON, Parquet, DataFrame")
    print("Each test downloads real Google Trends data (4 hour window)")

    results = []

    # Run all tests
    results.append(("CSV", test_csv_format()))
    results.append(("JSON", test_json_format()))
    results.append(("Parquet", test_parquet_format()))
    results.append(("DataFrame", test_dataframe_format()))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:12} {status}")

    print("-"*70)
    print(f"TOTAL: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n🎉 All tests passed! Output format support is working perfectly.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
