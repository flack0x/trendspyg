#!/usr/bin/env python3
"""
Command-line interface for trendspyg.

Provides easy access to Google Trends data via terminal commands.
"""

import sys
from typing import Optional

try:
    import click
except ImportError:
    print("Error: click is required for CLI functionality")
    print("Install with: pip install trendspyg[cli]")
    sys.exit(1)

from .config import COUNTRIES, US_STATES, CATEGORIES, TIME_PERIODS, SORT_OPTIONS
from .downloader import download_google_trends_csv
from .rss_downloader import download_google_trends_rss


@click.group()
@click.version_option(version="0.4.2", prog_name="trendspyg")
def cli() -> None:
    """
    trendspyg - Google Trends data downloader

    Free, open-source tool for downloading Google Trends data.
    Supports 125 countries, 51 US states, 20 categories.
    """
    pass


@cli.command()
@click.option(
    '--geo',
    default='US',
    help='Country/region code (e.g., US, GB, US-CA)',
    show_default=True
)
@click.option(
    '--output',
    type=click.Choice(['dict', 'dataframe', 'json', 'csv'], case_sensitive=False),
    default='dict',
    help='Output format',
    show_default=True
)
@click.option(
    '--no-images',
    is_flag=True,
    help='Exclude images from output'
)
@click.option(
    '--no-articles',
    is_flag=True,
    help='Exclude news articles from output'
)
@click.option(
    '--max-articles',
    type=int,
    default=5,
    help='Maximum articles per trend',
    show_default=True
)
def rss(
    geo: str,
    output: str,
    no_images: bool,
    no_articles: bool,
    max_articles: int
) -> None:
    """
    Download trends via RSS feed (fast, rich media).

    Examples:
        trendspyg rss --geo US
        trendspyg rss --geo GB --output json
        trendspyg rss --geo JP --no-images --no-articles
    """
    click.echo(f"Downloading RSS trends for {geo}...")

    try:
        result = download_google_trends_rss(
            geo=geo,
            output_format=output,
            include_images=not no_images,
            include_articles=not no_articles,
            max_articles_per_trend=max_articles
        )

        if output == 'dict':
            click.echo(f"\nFound {len(result)} trends:\n")
            click.echo("="*70)
            for i, trend in enumerate(result, 1):
                click.echo(f"\n{i}. {trend['trend'].upper()}")
                click.echo(f"   Traffic: {trend['traffic']}")
                click.echo(f"   Published: {trend['published']}")

                if 'image' in trend and trend['image']['url']:
                    click.echo(f"   Image: {trend['image']['source']}")

                if 'news_articles' in trend and trend['news_articles']:
                    click.echo(f"   News Articles ({len(trend['news_articles'])}):")
                    for j, article in enumerate(trend['news_articles'][:3], 1):
                        click.echo(f"     {j}. {article['headline']}")
                        click.echo(f"        Source: {article['source']}")
                        if j < len(trend['news_articles'][:3]):
                            click.echo("")
                    if len(trend['news_articles']) > 3:
                        click.echo(f"     ... and {len(trend['news_articles']) - 3} more articles")

                click.echo(f"   Explore: {trend['explore_link']}")

                if i < len(result):
                    click.echo("-"*70)
        elif output == 'dataframe':
            click.echo(f"\nDataFrame with {len(result)} rows")
            click.echo(result.to_string(max_rows=5))
        elif output == 'json':
            click.echo(result)
        elif output == 'csv':
            click.echo(result)

        click.echo(f"\n[OK] Success!")

    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--geo',
    default='US',
    help='Country/region code (e.g., US, GB, US-CA)',
    show_default=True
)
@click.option(
    '--hours',
    type=click.Choice(['4', '24', '48', '168'], case_sensitive=False),
    default='24',
    help='Time period in hours',
    show_default=True
)
@click.option(
    '--category',
    default='all',
    help='Category filter (e.g., sports, tech, health)',
    show_default=True
)
@click.option(
    '--output',
    type=click.Choice(['csv', 'json', 'dataframe', 'parquet'], case_sensitive=False),
    default='csv',
    help='Output format',
    show_default=True
)
@click.option(
    '--active-only',
    is_flag=True,
    help='Show only active/rising trends'
)
@click.option(
    '--sort',
    type=click.Choice(SORT_OPTIONS, case_sensitive=False),
    default='relevance',
    help='Sort order',
    show_default=True
)
@click.option(
    '--output-dir',
    type=click.Path(),
    default='./downloads',
    help='Output directory for files',
    show_default=True
)
def csv(
    geo: str,
    hours: str,
    category: str,
    output: str,
    active_only: bool,
    sort: str,
    output_dir: str
) -> None:
    """
    Download trends via CSV export (comprehensive, filtered).

    Examples:
        trendspyg csv --geo US
        trendspyg csv --geo US-CA --hours 168 --category sports
        trendspyg csv --geo GB --active-only --output json
    """
    click.echo(f"Downloading CSV trends for {geo}...")
    click.echo(f"  Time period: {hours}h")
    click.echo(f"  Category: {category}")
    click.echo(f"  Active only: {active_only}")

    try:
        result = download_google_trends_csv(
            geo=geo,
            hours=int(hours),
            category=category,
            output_format=output,
            active_only=active_only,
            sort_by=sort,
            download_dir=output_dir
        )

        if output == 'csv':
            click.echo(f"\n[OK] Downloaded: {result}")
        elif output == 'json':
            click.echo(f"\n[OK] Downloaded: {result}")
        elif output == 'parquet':
            click.echo(f"\n[OK] Downloaded: {result}")
        elif output == 'dataframe':
            click.echo(f"\nTop 10 Trends (Total: {len(result)}):\n")
            click.echo("="*100)

            # Show first 10 trends with details
            for i, (idx, row) in enumerate(result.head(10).iterrows(), 1):
                click.echo(f"\n{i}. {row['Trends'].upper()}")
                click.echo(f"   Search Volume: {row['Search volume']}")
                if 'Started' in row and row['Started']:
                    click.echo(f"   Started: {row['Started']}")
                if 'Trend breakdown' in row and row['Trend breakdown']:
                    breakdown = row['Trend breakdown']
                    if len(str(breakdown)) > 100:
                        breakdown = str(breakdown)[:100] + "..."
                    click.echo(f"   Related: {breakdown}")
                click.echo(f"   Explore: {row['Explore link']}")

                if i < 10 and i < len(result):
                    click.echo("-"*100)

            if len(result) > 10:
                click.echo(f"\n... and {len(result) - 10} more trends")

            click.echo(f"\n[OK] Total: {len(result)} trends")

    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--type',
    'list_type',
    type=click.Choice(['countries', 'states', 'categories', 'hours'], case_sensitive=False),
    required=True,
    help='Type of list to show'
)
def list(list_type: str) -> None:
    """
    List available options.

    Examples:
        trendspyg list --type countries
        trendspyg list --type states
        trendspyg list --type categories
    """
    if list_type == 'countries':
        click.echo(f"\nAvailable Countries ({len(COUNTRIES)}):\n")
        for code, name in sorted(COUNTRIES.items()):
            click.echo(f"  {code:4} - {name}")

    elif list_type == 'states':
        click.echo(f"\nAvailable US States ({len(US_STATES)}):\n")
        for code, name in sorted(US_STATES.items()):
            click.echo(f"  {code:8} - {name}")

    elif list_type == 'categories':
        click.echo(f"\nAvailable Categories ({len(CATEGORIES)}):\n")
        for cat in sorted(CATEGORIES.keys()):
            click.echo(f"  {cat}")

    elif list_type == 'hours':
        click.echo("\nAvailable Time Periods:\n")
        for hours, label in TIME_PERIODS.items():
            click.echo(f"  {hours:3} hours - {label}")


@cli.command()
def info() -> None:
    """Show package information and statistics."""
    click.echo("\n" + "="*60)
    click.echo("trendspyg - Google Trends Data Downloader")
    click.echo("="*60)
    click.echo(f"\nVersion: 0.3.0")
    click.echo(f"License: MIT")
    click.echo(f"Homepage: https://github.com/flack0x/trendspyg")
    click.echo(f"\nSupported Options:")
    click.echo(f"  Countries:  {len(COUNTRIES)}")
    click.echo(f"  US States:  {len(US_STATES)}")
    click.echo(f"  Categories: {len(CATEGORIES)}")
    click.echo(f"  Time Periods: {len(TIME_PERIODS)}")
    click.echo(f"  Sort Options: {len(SORT_OPTIONS)}")
    click.echo(f"\nTotal Configurations: 188,000+")
    click.echo(f"\nData Sources:")
    click.echo(f"  RSS:  Fast (0.2s), rich media, ~10-20 trends")
    click.echo(f"  CSV:  Comprehensive (10s), filtered, ~360+ trends")
    click.echo("\n" + "="*60)


def main() -> None:
    """Main entry point for CLI."""
    cli()


if __name__ == '__main__':
    main()
