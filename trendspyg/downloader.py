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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime


# Category mapping (internal Google names)
CATEGORIES = {
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
TIME_PERIODS = {
    '4h': 4,
    '24h': 24,
    '48h': 48,
    '7d': 168  # 7 days = 168 hours
}

# Sort options
SORT_OPTIONS = ['relevance', 'title', 'volume', 'recency']


def download_google_trends_csv(geo='US', hours=24, category='all', active_only=False,
                               sort_by='relevance', headless=True, download_dir=None):
    """
    Download Google Trends CSV with configurable filters

    Args:
        geo (str): Country code (US, CA, UK, IN, JP, etc.)
        hours (int): Time period in hours (4, 24, 48, 168)
        category (str): Category filter (all, sports, entertainment, etc.)
        active_only (bool): Show only active trends
        sort_by (str): Sort criteria (relevance, title, volume, recency)
        headless (bool): Run browser in headless mode
        download_dir (str): Directory to save file

    Returns:
        str: Path to downloaded file or None if failed
    """

    # Setup download directory
    if download_dir is None:
        download_dir = os.path.join(os.path.dirname(__file__), '..', 'downloads')
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

    driver = webdriver.Chrome(options=chrome_options)

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
        time.sleep(3)  # Wait for page to load

        # Apply filters via UI if needed

        # 1. Toggle "Active trends only" if requested
        if active_only:
            try:
                print("[INFO] Enabling 'Active trends only' filter...")
                active_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'All trends')]"))
                )
                active_button.click()
                time.sleep(0.5)

                # Click the toggle switch
                toggle = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[role="switch"]'))
                )
                driver.execute_script("arguments[0].click();", toggle)
                time.sleep(1)

                # Click somewhere else to close menu
                driver.find_element(By.TAG_NAME, 'body').click()
                time.sleep(0.5)
            except Exception as e:
                print(f"[WARN] Could not toggle active trends: {e}")

        # 2. Apply sort if not default (relevance)
        if sort_by.lower() != 'relevance':
            try:
                print(f"[INFO] Sorting by: {sort_by}...")
                # Wait a bit longer for page to fully load
                time.sleep(2)

                sort_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'relevance') or contains(., 'Relevance')]"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", sort_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", sort_button)
                time.sleep(1)

                # Click the sort option
                if sort_by.lower() == 'title':
                    sort_option = driver.find_element(By.XPATH, "//div[@role='menuitemradio'][contains(., 'Title')]")
                elif sort_by.lower() == 'volume':
                    sort_option = driver.find_element(By.XPATH, "//div[@role='menuitemradio'][contains(., 'Search volume')]")
                elif sort_by.lower() == 'recency':
                    sort_option = driver.find_element(By.XPATH, "//div[@role='menuitemradio'][contains(., 'Recency')]")
                else:
                    sort_option = driver.find_element(By.XPATH, "//div[@role='menuitemradio'][contains(., 'Relevance')]")

                driver.execute_script("arguments[0].click();", sort_option)
                time.sleep(1)
            except Exception as e:
                print(f"[WARN] Could not apply sort (will use default): {str(e)[:100]}")

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

        # Wait for download
        time.sleep(5)

        # Find new file
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
            return new_path
        else:
            print("[FAIL] No new file detected")
            return None

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return None

    finally:
        driver.quit()


def main():
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
