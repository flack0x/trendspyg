#!/usr/bin/env python3
"""
Configurable Google Trends CSV Downloader
Download trends with custom filters: location, time period, category, sort, etc.

Usage Examples:
    # Download US trends from past 24 hours
    py download_trends_configurable.py

    # Download Canada trends from past 4 hours, Sports only
    py download_trends_configurable.py --geo CA --hours 4 --category sports

    # Download UK trends from past 7 days, sorted by search volume
    py download_trends_configurable.py --geo UK --hours 168 --sort volume
"""

import os
import time
import argparse
from typing import Optional, Callable, Any, Dict, Set, List, Literal, Union, TYPE_CHECKING
from selenium import webdriver

if TYPE_CHECKING:
    import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    ElementClickInterceptedException
)
from datetime import datetime

# Import config and exceptions
from .config import COUNTRIES, US_STATES
from .exceptions import (
    InvalidParameterError,
    BrowserError,
    DownloadError
)

# Type aliases
OutputFormat = Literal['csv', 'json', 'parquet', 'dataframe']
SortOption = Literal['relevance', 'title', 'volume', 'recency']


# Category mapping (internal Google names)
CATEGORIES: Dict[str, str] = {
    'all': '',
    'autos': 'autos',
    'beauty': 'beauty',
    'business': 'business',
    'climate': 'climate',
    'entertainment': 'entertainment',
    'food': 'food',
    'games': 'games',
    'health': 'health',
    'hobbies': 'hobbies',
    'jobs': 'jobs',
    'law': 'law',
    'other': 'other',
    'pets': 'pets',
    'politics': 'politics',
    'science': 'science',
    'shopping': 'shopping',
    'sports': 'sports',
    'technology': 'tech',
    'travel': 'travel'
}

# Time period options (in hours)
TIME_PERIODS: Dict[str, int] = {
    '4h': 4,
    '24h': 24,
    '48h': 48,
    '7d': 168  # 7 days = 168 hours
}

# Sort options
SORT_OPTIONS: List[str] = ['relevance', 'title', 'volume', 'recency']


def _download_with_retry(download_func: Callable[[], Any], max_retries: int = 3) -> Any:
    """Wrapper to retry download with exponential backoff.

    Args:
        download_func: Function to call for download
        max_retries: Maximum number of retry attempts

    Returns:
        Result of download_func

    Raises:
        Last exception if all retries fail
    """
    for attempt in range(max_retries):
        try:
            return download_func()
        except (BrowserError, DownloadError, TimeoutException) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"[WARN] Attempt {attempt + 1} failed: {type(e).__name__}")
                print(f"[INFO] Retrying in {wait_time}s... ({attempt + 2}/{max_retries})")
                time.sleep(wait_time)
            else:
                # Last attempt failed, re-raise
                print(f"[ERROR] All {max_retries} attempts failed")
                raise


def validate_geo(geo: str) -> str:
    """Validate geo parameter against available countries and US states.

    Args:
        geo: Country or US state code

    Raises:
        InvalidParameterError: If geo code is invalid

    Returns:
        Validated geo code (uppercased)
    """
    geo = geo.upper()

    if geo in COUNTRIES or geo in US_STATES:
        return geo

    # Try to find similar matches for helpful error message
    similar = [code for code in list(COUNTRIES.keys()) + list(US_STATES.keys())
               if code.startswith(geo[0]) if len(geo) > 0][:5]

    error_msg = f"Invalid geo code '{geo}'."
    if similar:
        error_msg += f" Did you mean one of: {', '.join(similar)}?"
    error_msg += f"\n\nAvailable: {len(COUNTRIES)} countries (US, CA, UK, DE, FR, ...) "
    error_msg += f"or {len(US_STATES)} US states (CA, NY, TX, FL, ...)"
    error_msg += "\n\nSee trendspyg.config.COUNTRIES and trendspyg.config.US_STATES for full list."

    raise InvalidParameterError(error_msg)


def validate_hours(hours: int) -> int:
    """Validate hours parameter against available time periods.

    Args:
        hours: Time period in hours

    Raises:
        InvalidParameterError: If hours value is invalid

    Returns:
        Validated hours value
    """
    valid_hours = [4, 24, 48, 168]

    if hours in valid_hours:
        return hours

    raise InvalidParameterError(
        f"Invalid hours value '{hours}'. Must be one of: {valid_hours}\n"
        f"  4   = Past 4 hours\n"
        f"  24  = Past 24 hours (1 day)\n"
        f"  48  = Past 48 hours (2 days)\n"
        f"  168 = Past 168 hours (7 days)"
    )


def validate_category(category: str) -> str:
    """Validate category parameter against available categories.

    Args:
        category: Category name

    Raises:
        InvalidParameterError: If category is invalid

    Returns:
        Validated category (lowercased)
    """
    category = category.lower()

    if category in CATEGORIES:
        return category

    # Try to find similar matches
    similar = [cat for cat in CATEGORIES.keys() if cat.startswith(category[:3]) if len(category) >= 3][:5]

    error_msg = f"Invalid category '{category}'."
    if similar:
        error_msg += f" Did you mean one of: {', '.join(similar)}?"
    error_msg += f"\n\nAvailable categories: {', '.join(sorted(CATEGORIES.keys()))}"

    raise InvalidParameterError(error_msg)


def _convert_csv_to_format(
    csv_path: str,
    output_format: OutputFormat,
    download_dir: str
) -> Union[str, 'pd.DataFrame']:
    """Convert downloaded CSV to requested output format.

    Args:
        csv_path: Path to the downloaded CSV file
        output_format: Desired output format
        download_dir: Directory for output files

    Returns:
        Path to converted file or DataFrame object

    Raises:
        ImportError: If required library is not installed
        DownloadError: If conversion fails
    """
    if output_format == 'csv':
        return csv_path

    # Import pandas for all non-CSV formats
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            f"pandas is required for '{output_format}' format.\n"
            "Install with: pip install trendspyg[analysis]"
        )

    # Read CSV
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        raise DownloadError(f"Failed to read CSV file: {e}")

    # Return DataFrame directly if requested
    if output_format == 'dataframe':
        return df

    # Convert to other formats
    base_path = csv_path.rsplit('.', 1)[0]  # Remove .csv extension

    if output_format == 'json':
        json_path = base_path + '.json'
        try:
            df.to_json(json_path, orient='records', indent=2)
            # Remove original CSV
            os.remove(csv_path)
            print(f"[OK] Converted to JSON: {os.path.basename(json_path)}")
            return json_path
        except Exception as e:
            raise DownloadError(f"Failed to convert to JSON: {e}")

    elif output_format == 'parquet':
        parquet_path = base_path + '.parquet'
        try:
            df.to_parquet(parquet_path, index=False)
            # Remove original CSV
            os.remove(csv_path)
            print(f"[OK] Converted to Parquet: {os.path.basename(parquet_path)}")
            return parquet_path
        except ImportError:
            raise ImportError(
                "pyarrow is required for parquet format.\n"
                "Install with: pip install pyarrow"
            )
        except Exception as e:
            raise DownloadError(f"Failed to convert to Parquet: {e}")

    # Should never reach here due to Literal type
    raise InvalidParameterError(f"Unsupported output format: {output_format}")


def download_google_trends_csv(
    geo: str = 'US',
    hours: int = 24,
    category: str = 'all',
    active_only: bool = False,
    sort_by: str = 'relevance',
    headless: bool = True,
    download_dir: Optional[str] = None,
    output_format: OutputFormat = 'csv'
) -> Union[str, 'pd.DataFrame', None]:
    """
    Download Google Trends data with configurable filters and output formats

    Args:
        geo: Country code (US, CA, UK, IN, JP, etc.)
        hours: Time period in hours (4, 24, 48, 168)
        category: Category filter (all, sports, entertainment, etc.)
        active_only: Show only active trends
        sort_by: Sort criteria (relevance, title, volume, recency)
        headless: Run browser in headless mode
        download_dir: Directory to save file
        output_format: Output format (csv, json, parquet, dataframe)

    Returns:
        Path to downloaded file (for csv/json/parquet) or DataFrame (for dataframe format),
        or None if failed

    Raises:
        InvalidParameterError: If any parameters are invalid
        BrowserError: If browser automation fails
        DownloadError: If file download fails
    """
    # Validate input parameters
    geo = validate_geo(geo)
    hours = validate_hours(hours)
    category = validate_category(category)

    # Setup download directory
    if download_dir is None:
        # Default to 'downloads' folder in current working directory
        download_dir = os.path.join(os.getcwd(), 'downloads')
    download_dir = os.path.abspath(download_dir)
    os.makedirs(download_dir, exist_ok=True)

    # Get existing files
    existing_files = set(f for f in os.listdir(download_dir) if f.endswith('.csv'))

    # Setup Chrome options
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

    # Suppress logging
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

    print(f"[INFO] Opening Google Trends...")
    print(f"       Location: {geo}")
    print(f"       Time: Past {hours} hours")
    print(f"       Category: {category}")
    print(f"       Active only: {active_only}")
    print(f"       Sort: {sort_by}")

    # Initialize browser with error handling
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except WebDriverException as e:
        raise BrowserError(
            f"Failed to start Chrome browser: {e}\n\n"
            "Please ensure:\n"
            "1. Chrome browser is installed\n"
            "2. ChromeDriver is compatible with your Chrome version\n"
            "3. You have proper permissions\n\n"
            "ChromeDriver is auto-downloaded by Selenium, but you need Chrome browser installed."
        )

    try:
        # Build URL with parameters
        url = f"https://trends.google.com/trending?geo={geo}"

        # Add time period if not default (24 hours)
        if hours != 24:
            url += f"&hours={hours}"

        # Add category if not 'all'
        cat_code = CATEGORIES.get(category.lower(), '')
        if cat_code:
            url += f"&cat={cat_code}"

        print(f"[INFO] Navigating to: {url}")
        driver.get(url)

        # Wait for page to load by checking for Export button
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Export')]"))
        )

        # Apply filters via UI if needed

        # 1. Toggle "Active trends only" if requested
        if active_only:
            try:
                print("[INFO] Enabling 'Active trends only' filter...")
                # Click the "All trends" button to open the menu
                active_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label*='select trend status']"))
                )
                active_button.click()
                time.sleep(0.5)

                # Click the toggle switch (it's a button with role="switch")
                toggle = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[role='switch'][aria-label='Show active trends only']"))
                )
                driver.execute_script("arguments[0].click();", toggle)
                time.sleep(1)

                # Press ESC to close menu
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(1)
            except (TimeoutException, NoSuchElementException) as e:
                print(f"[WARN] Could not toggle 'Active trends only' filter - using all trends")
                print(f"       Reason: UI element not found (Google may have changed their interface)")

        # 2. Apply sort if not default (relevance)
        # NOTE: Sort appears to only affect UI table display, not CSV export order
        # CSV always exports in relevance order regardless of sort selection
        if sort_by.lower() != 'relevance':
            print(f"[INFO] Note: Sort by '{sort_by}' only affects UI display (CSV exports in relevance order)")

        # Click Export button
        print("[INFO] Downloading CSV...")
        export_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Export')]"))
        )
        export_button.click()
        time.sleep(1)

        # Click Download CSV
        download_csv = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'li[data-action="csv"]'))
        )
        driver.execute_script("arguments[0].click();", download_csv)

        # Wait for download with dynamic file checking
        print("[INFO] Waiting for file download...")
        max_wait_time = 10  # Maximum 10 seconds
        check_interval = 0.5  # Check every 0.5 seconds
        elapsed_time = 0.0  # Use float to match check_interval type
        new_files: Set[str] = set()

        while elapsed_time < max_wait_time:
            time.sleep(check_interval)
            elapsed_time += check_interval

            # Check for new files
            current_files = set(f for f in os.listdir(download_dir) if f.endswith('.csv'))
            new_files = current_files - existing_files

            if new_files:
                print(f"[INFO] File detected after {elapsed_time:.1f}s")
                break

        # Final check if loop ended without finding file
        if not new_files:
            current_files = set(f for f in os.listdir(download_dir) if f.endswith('.csv'))
            new_files = current_files - existing_files

        if new_files:
            downloaded_file = list(new_files)[0]
            full_path = os.path.join(download_dir, downloaded_file)

            # Rename file with configuration info
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            new_name = f"trends_{geo}_{hours}h_{category}_{timestamp}.csv"
            new_path = os.path.join(download_dir, new_name)

            os.rename(full_path, new_path)

            print(f"[OK] Downloaded: {new_name}")
            print(f"[OK] Location: {new_path}")

            # Convert to requested format
            result = _convert_csv_to_format(new_path, output_format, download_dir)

            # Print success message based on format
            if output_format == 'dataframe':
                print(f"[OK] Converted to DataFrame with {len(result)} rows")

            return result
        else:
            raise DownloadError(
                "No new file detected after download attempt.\n\n"
                "Possible causes:\n"
                "- Download may have failed silently\n"
                "- File may have been downloaded to a different location\n"
                "- Network timeout during download\n\n"
                f"Expected download directory: {download_dir}"
            )

    except TimeoutException as e:
        raise BrowserError(
            f"Page load timeout: {e}\n\n"
            "Possible causes:\n"
            "- Slow internet connection\n"
            "- Google Trends website is down or slow\n"
            "- Network firewall blocking access\n\n"
            "Try again with a better connection or check https://trends.google.com/trending"
        )

    except NoSuchElementException as e:
        raise BrowserError(
            f"Could not find UI element: {e}\n\n"
            "Possible causes:\n"
            "- Google Trends changed their website design\n"
            "- Page did not load correctly\n\n"
            "Solutions:\n"
            "- Update trendspyg: pip install --upgrade trendspyg\n"
            "- Check GitHub issues: https://github.com/flack0x/trendspyg/issues\n"
            "- Report this issue if it persists"
        )

    except ElementClickInterceptedException as e:
        raise BrowserError(
            f"Could not click UI element: {e}\n\n"
            "An element is blocking the click. This may be temporary.\n"
            "Try running again - this often resolves automatically."
        )

    except (InvalidParameterError, BrowserError, DownloadError):
        # Re-raise our custom exceptions without wrapping
        raise

    except Exception as e:
        # Catch any other unexpected errors
        raise BrowserError(
            f"Unexpected error during download: {type(e).__name__}: {e}\n\n"
            "This is an unexpected error. Please report it at:\n"
            "https://github.com/flack0x/trendspyg/issues"
        )

    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Download Google Trends data with custom filters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default (US, past 24 hours, all categories)
  %(prog)s

  # Canada, past 4 hours
  %(prog)s --geo CA --hours 4

  # UK, past 7 days, Sports only, sorted by volume
  %(prog)s --geo UK --hours 168 --category sports --sort volume

  # India, active trends only
  %(prog)s --geo IN --active-only

  # Japan, Entertainment category, sorted by recency
  %(prog)s --geo JP --category entertainment --sort recency

Available countries (geo codes):
  US, CA, UK, AU, IN, JP, DE, FR, BR, MX, ES, IT, RU, KR, and many more

Available categories:
  all, sports, entertainment, business, politics, technology, health,
  science, games, shopping, food, travel, beauty, hobbies, climate, etc.
        """
    )

    parser.add_argument('--geo', type=str, default='US',
                       help='Country code (US, CA, UK, IN, JP, etc.). Default: US')

    parser.add_argument('--hours', type=int, choices=[4, 24, 48, 168], default=24,
                       help='Time period: 4 (4h), 24 (24h), 48 (48h), 168 (7d). Default: 24')

    parser.add_argument('--category', type=str, choices=list(CATEGORIES.keys()), default='all',
                       help='Category filter. Default: all')

    parser.add_argument('--active-only', action='store_true',
                       help='Show only active trends')

    parser.add_argument('--sort', type=str, choices=SORT_OPTIONS, default='relevance',
                       help='Sort by: relevance, title, volume, recency. Default: relevance')

    parser.add_argument('--visible', action='store_true',
                       help='Run browser in visible mode (not headless)')

    parser.add_argument('--output-dir', type=str,
                       help='Output directory for downloaded file')

    args = parser.parse_args()

    print("="*70)
    print("Google Trends Configurable Downloader")
    print("="*70)

    filepath = download_google_trends_csv(
        geo=args.geo.upper(),
        hours=args.hours,
        category=args.category,
        active_only=args.active_only,
        sort_by=args.sort,
        headless=not args.visible,
        download_dir=args.output_dir
    )

    print("="*70)

    if filepath:
        size = os.path.getsize(filepath)
        print(f"File size: {size:,} bytes")
        print("\nDone!")
        exit(0)
    else:
        print("\nFailed to download")
        exit(1)


if __name__ == "__main__":
    main()
