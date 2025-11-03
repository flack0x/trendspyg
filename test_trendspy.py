"""Comprehensive test suite for trendspyg package."""

import sys
import time
from datetime import datetime

def print_section(title):
    """Print section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)

def test_imports():
    """Test all package imports."""
    print_section("TEST 1: Package Imports")

    results = []

    # Test main package
    try:
        import trendspyg
        print(f"[OK] trendspyg v{trendspyg.__version__}")
        results.append(('Main package', True, None))
    except Exception as e:
        print(f"[FAIL] trendspyg: {e}")
        results.append(('Main package', False, str(e)))

    # Test all submodules
    modules = ['config', 'exceptions', 'utils', 'version', 'downloader']
    for module in modules:
        try:
            exec(f"from trendspyg import {module}")
            print(f"[OK] trendspyg.{module}")
            results.append((f'Module: {module}', True, None))
        except Exception as e:
            print(f"[FAIL] trendspyg.{module}: {e}")
            results.append((f'Module: {module}', False, str(e)))

    return results

def test_configuration():
    """Test configuration data."""
    print_section("TEST 2: Configuration System")

    results = []

    try:
        from trendspyg.config import (
            CATEGORIES, COUNTRIES, US_STATES,
            TIME_PERIODS, SORT_OPTIONS,
            DEFAULT_GEO, DEFAULT_HOURS, DEFAULT_CATEGORY
        )

        # Test counts
        tests = [
            ('Countries count', len(COUNTRIES), 114, '>='),
            ('US States count', len(US_STATES), 51, '=='),
            ('Categories count', len(CATEGORIES), 20, '=='),
            ('Time periods count', len(TIME_PERIODS), 4, '=='),
            ('Sort options count', len(SORT_OPTIONS), 4, '=='),
        ]

        for name, actual, expected, op in tests:
            if op == '==':
                passed = actual == expected
            elif op == '>=':
                passed = actual >= expected
            else:
                passed = False

            status = '[OK]' if passed else '[FAIL]'
            print(f"{status} {name}: {actual} (expected {op} {expected})")
            results.append((name, passed, f'{actual} vs {expected}'))

        # Test data validity
        print("\nSample data validation:")
        samples = [
            ('COUNTRIES["US"]', COUNTRIES.get('US'), 'United States'),
            ('COUNTRIES["CA"]', COUNTRIES.get('CA'), 'Canada'),
            ('US_STATES["US-CA"]', US_STATES.get('US-CA'), 'California'),
            ('CATEGORIES["sports"]', CATEGORIES.get('sports'), 'sports'),
            ('CATEGORIES["technology"]', CATEGORIES.get('technology'), 'tech'),
            ('TIME_PERIODS[24]', TIME_PERIODS.get(24), '24h'),
            ('DEFAULT_GEO', DEFAULT_GEO, 'US'),
            ('DEFAULT_HOURS', DEFAULT_HOURS, 24),
        ]

        for name, actual, expected in samples:
            passed = actual == expected
            status = '[OK]' if passed else '[FAIL]'
            print(f"  {status} {name} = {actual!r}")
            results.append((name, passed, None))

    except Exception as e:
        print(f"[FAIL] Configuration test error: {e}")
        results.append(('Configuration system', False, str(e)))

    return results

def test_exceptions():
    """Test custom exceptions."""
    print_section("TEST 3: Exception Classes")

    results = []

    try:
        from trendspyg.exceptions import (
            TrendspyException, DownloadError, RateLimitError,
            InvalidParameterError, BrowserError, ParseError
        )

        exceptions = [
            'TrendspyException', 'DownloadError', 'RateLimitError',
            'InvalidParameterError', 'BrowserError', 'ParseError'
        ]

        for exc_name in exceptions:
            try:
                exc_class = eval(exc_name)
                # Test instantiation
                exc_instance = exc_class("Test error")
                # Test inheritance
                is_exception = isinstance(exc_instance, Exception)
                status = '[OK]' if is_exception else '[FAIL]'
                print(f"{status} {exc_name} inherits from Exception")
                results.append((exc_name, is_exception, None))
            except Exception as e:
                print(f"[FAIL] {exc_name}: {e}")
                results.append((exc_name, False, str(e)))

    except Exception as e:
        print(f"[FAIL] Exceptions test error: {e}")
        results.append(('Exception classes', False, str(e)))

    return results

def test_utils():
    """Test utility functions."""
    print_section("TEST 4: Utility Functions")

    results = []

    try:
        from trendspyg.utils import get_timestamp, ensure_dir
        import os

        # Test get_timestamp
        timestamp = get_timestamp()
        print(f"[INFO] get_timestamp() = {timestamp}")
        # Check format (YYYYMMDD-HHMMSS)
        valid_format = len(timestamp) == 15 and timestamp[8] == '-'
        status = '[OK]' if valid_format else '[FAIL]'
        print(f"{status} Timestamp format valid")
        results.append(('get_timestamp format', valid_format, timestamp))

        # Test ensure_dir
        test_dir = os.path.join(os.getcwd(), 'test_temp_dir')
        result_dir = ensure_dir(test_dir)
        dir_created = os.path.exists(test_dir)
        status = '[OK]' if dir_created else '[FAIL]'
        print(f"{status} ensure_dir() creates directory")
        results.append(('ensure_dir creates dir', dir_created, None))

        # Cleanup
        if dir_created:
            os.rmdir(test_dir)
            print("[INFO] Test directory cleaned up")

    except Exception as e:
        print(f"[FAIL] Utils test error: {e}")
        results.append(('Utility functions', False, str(e)))

    return results

def test_downloader_api():
    """Test downloader function signature and parameters."""
    print_section("TEST 5: Downloader API")

    results = []

    try:
        from trendspyg.downloader import download_google_trends_csv
        import inspect

        # Test function signature
        sig = inspect.signature(download_google_trends_csv)
        params = list(sig.parameters.keys())

        expected_params = ['geo', 'hours', 'category', 'active_only',
                          'sort_by', 'headless', 'download_dir']

        print(f"[INFO] Function parameters: {params}")

        params_match = params == expected_params
        status = '[OK]' if params_match else '[FAIL]'
        print(f"{status} Function signature matches specification")
        results.append(('Function signature', params_match, None))

        # Test default values
        defaults = {
            'geo': 'US',
            'hours': 24,
            'category': 'all',
            'active_only': False,
            'sort_by': 'relevance',
            'headless': True,
            'download_dir': None
        }

        print("\n[INFO] Testing default parameter values:")
        for param_name, expected_default in defaults.items():
            param = sig.parameters[param_name]
            actual_default = param.default if param.default != inspect.Parameter.empty else None
            match = actual_default == expected_default
            status = '[OK]' if match else '[FAIL]'
            print(f"  {status} {param_name} = {actual_default!r} (expected {expected_default!r})")
            results.append((f'Default: {param_name}', match, None))

    except Exception as e:
        print(f"[FAIL] Downloader API test error: {e}")
        results.append(('Downloader API', False, str(e)))

    return results

def test_package_metadata():
    """Test package metadata."""
    print_section("TEST 6: Package Metadata")

    results = []

    try:
        import trendspyg

        # Test metadata attributes
        attrs = ['__version__', '__author__', '__license__']

        for attr in attrs:
            value = getattr(trendspyg, attr, None)
            exists = value is not None
            status = '[OK]' if exists else '[FAIL]'
            print(f"{status} {attr} = {value!r}")
            results.append((attr, exists, value))

        # Test version format
        version = trendspyg.__version__
        version_valid = len(version.split('.')) == 3
        status = '[OK]' if version_valid else '[FAIL]'
        print(f"{status} Version format is semantic (X.Y.Z)")
        results.append(('Version format', version_valid, version))

    except Exception as e:
        print(f"[FAIL] Metadata test error: {e}")
        results.append(('Package metadata', False, str(e)))

    return results

def generate_report(all_results):
    """Generate comprehensive test report."""
    print_section("COMPREHENSIVE TEST REPORT")

    # Calculate statistics
    total_tests = sum(len(results) for results in all_results.values())
    passed_tests = sum(sum(1 for _, passed, _ in results if passed)
                      for results in all_results.values())
    failed_tests = total_tests - passed_tests
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

    print(f"\nTotal Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Pass Rate: {pass_rate:.1f}%")

    # Detailed results by category
    print("\nDetailed Results:")
    for category, results in all_results.items():
        cat_passed = sum(1 for _, passed, _ in results if passed)
        cat_total = len(results)
        cat_rate = (cat_passed / cat_total * 100) if cat_total > 0 else 0
        status = '[OK]' if cat_rate == 100 else '[WARN]' if cat_rate >= 50 else '[FAIL]'
        print(f"\n{status} {category}: {cat_passed}/{cat_total} ({cat_rate:.0f}%)")

        # Show failures
        failures = [(name, error) for name, passed, error in results if not passed]
        if failures:
            print("  Failures:")
            for name, error in failures:
                print(f"    - {name}: {error}")

    # Overall rating
    print("\n" + "="*70)
    print("OVERALL RATING")
    print("="*70)

    if pass_rate >= 90:
        grade = "A (Excellent)"
        emoji = "[EXCELLENT]"
    elif pass_rate >= 75:
        grade = "B (Good)"
        emoji = "[GOOD]"
    elif pass_rate >= 60:
        grade = "C (Fair)"
        emoji = "[FAIR]"
    else:
        grade = "F (Poor)"
        emoji = "[NEEDS WORK]"

    print(f"\n{emoji} Grade: {grade}")
    print(f"Pass Rate: {pass_rate:.1f}%")

    # Specific ratings
    print("\nComponent Ratings:")

    components = {
        'Import System': all_results.get('Imports', []),
        'Configuration': all_results.get('Configuration', []),
        'Error Handling': all_results.get('Exceptions', []),
        'Utility Functions': all_results.get('Utils', []),
        'API Design': all_results.get('Downloader API', []),
        'Package Metadata': all_results.get('Metadata', []),
    }

    for comp_name, comp_results in components.items():
        if not comp_results:
            continue
        comp_passed = sum(1 for _, passed, _ in comp_results if passed)
        comp_total = len(comp_results)
        comp_rate = (comp_passed / comp_total * 100) if comp_total > 0 else 0

        if comp_rate >= 90:
            rating = "5/5 stars"
        elif comp_rate >= 75:
            rating = "4/5 stars"
        elif comp_rate >= 60:
            rating = "3/5 stars"
        elif comp_rate >= 40:
            rating = "2/5 stars"
        else:
            rating = "1/5 stars"

        print(f"  {comp_name}: {rating} ({comp_rate:.0f}%)")

    return pass_rate, grade

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("  TRENDSPY PACKAGE - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    all_results = {}

    # Run all test suites
    all_results['Imports'] = test_imports()
    all_results['Configuration'] = test_configuration()
    all_results['Exceptions'] = test_exceptions()
    all_results['Utils'] = test_utils()
    all_results['Downloader API'] = test_downloader_api()
    all_results['Metadata'] = test_package_metadata()

    # Generate final report
    pass_rate, grade = generate_report(all_results)

    print("\n" + "="*70)
    print(f"Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Exit with appropriate code
    sys.exit(0 if pass_rate >= 80 else 1)

if __name__ == '__main__':
    main()
