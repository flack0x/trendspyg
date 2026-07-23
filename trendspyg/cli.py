#!/usr/bin/env python3
"""
Command-line interface for trendspyg.

Provides easy access to Google Trends data via terminal commands.
"""

import sys
from typing import Any, Dict, List, cast

try:
    import click
except ImportError:
    print("Error: click is required for CLI functionality")
    print("Install with: pip install trendspyg[cli]")
    sys.exit(1)

from .config import CATEGORIES, COUNTRIES, SORT_OPTIONS, TIME_PERIODS, US_STATES
from .downloader import download_google_trends_csv
from .explore import (
    download_google_trends_comparison,
    download_google_trends_explore,
    download_google_trends_interest_over_time,
)
from .rss_downloader import download_google_trends_rss
from .version import __version__


def _configure_stdout_encoding() -> None:
    """Force UTF-8 on stdout/stderr so non-ASCII trend data renders on Windows.

    Fails open: older Pythons or redirected streams without reconfigure() are skipped.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


@click.group()
@click.version_option(version=__version__, prog_name="trendspyg")
def cli() -> None:
    """
    trendspyg - Google Trends data downloader

    Free, open-source tool for downloading Google Trends data.
    Supports 125 countries, 51 US states, 20 categories.
    """
    pass


@cli.command()
@click.option(
    "--geo", default="US", help="Country/region code (e.g., US, GB, US-CA)", show_default=True
)
@click.option(
    "--output",
    type=click.Choice(["dict", "dataframe", "json", "csv"], case_sensitive=False),
    default="dict",
    help="Output format",
    show_default=True,
)
@click.option("--no-images", is_flag=True, help="Exclude images from output")
@click.option("--no-articles", is_flag=True, help="Exclude news articles from output")
@click.option(
    "--max-articles", type=int, default=5, help="Maximum articles per trend", show_default=True
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress human-readable banners; print only the requested output (pipe-safe).",
)
@click.option(
    "--envelope",
    is_flag=True,
    help="Wrap output in {fetched_at, geo, count, trends: [...]}. Only affects --output json/dict.",
)
@click.option(
    "--normalize",
    is_flag=True,
    help="Return the unified agent-friendly NormalizedEnvelope as JSON (ignores --output).",
)
def rss(
    geo: str,
    output: str,
    no_images: bool,
    no_articles: bool,
    max_articles: int,
    quiet: bool,
    envelope: bool,
    normalize: bool,
) -> None:
    """
    Download trends via RSS feed (fast, rich media).

    Examples:
        trendspyg rss --geo US
        trendspyg rss --geo GB --output json
        trendspyg rss --geo JP --no-images --no-articles
        trendspyg rss --geo US --output json --quiet | jq .
        trendspyg rss --geo US --output json --quiet --envelope
    """
    if not quiet and not normalize:
        click.echo(f"Downloading RSS trends for {geo}...")

    try:
        result = download_google_trends_rss(
            geo=geo,
            output_format=cast(Any, output),
            include_images=not no_images,
            include_articles=not no_articles,
            max_articles_per_trend=max_articles,
            normalize=normalize,
        )

        if normalize:
            import json as _json

            click.echo(_json.dumps(result, indent=2, default=str))
            return

        if envelope and output in ("dict", "json"):
            import json as _json
            from datetime import datetime, timezone

            if output == "dict":
                trends_list = cast(List[Dict[str, Any]], result)
            else:
                trends_list = _json.loads(cast(str, result))
            wrapped = {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "geo": geo,
                "count": len(trends_list),
                "trends": trends_list,
            }
            if output == "json":
                click.echo(_json.dumps(wrapped, indent=2, default=str))
            else:
                click.echo(wrapped)
            return

        result = cast(Any, result)
        if output == "dict":
            if quiet:
                click.echo(result)
            else:
                click.echo(f"\nFound {len(result)} trends:\n")
                click.echo("=" * 70)
                for i, trend in enumerate(result, 1):
                    click.echo(f"\n{i}. {trend['trend'].upper()}")
                    click.echo(f"   Traffic: {trend['traffic']}")
                    click.echo(f"   Published: {trend['published']}")

                    if "image" in trend and trend["image"]["url"]:
                        click.echo(f"   Image: {trend['image']['source']}")

                    if "news_articles" in trend and trend["news_articles"]:
                        click.echo(f"   News Articles ({len(trend['news_articles'])}):")
                        for j, article in enumerate(trend["news_articles"][:3], 1):
                            click.echo(f"     {j}. {article['headline']}")
                            click.echo(f"        Source: {article['source']}")
                            if j < len(trend["news_articles"][:3]):
                                click.echo("")
                        if len(trend["news_articles"]) > 3:
                            click.echo(
                                f"     ... and {len(trend['news_articles']) - 3} more articles"
                            )

                    click.echo(f"   Explore: {trend['explore_link']}")

                    if i < len(result):
                        click.echo("-" * 70)
        elif output == "dataframe":
            if not quiet:
                click.echo(f"\nDataFrame with {len(result)} rows")
            click.echo(result.to_string(max_rows=5) if not quiet else result.to_string())
        elif output == "json":
            click.echo(result)
        elif output == "csv":
            click.echo(result)

        if not quiet:
            click.echo("\n[OK] Success!")

    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--geo", default="US", help="Country/region code (e.g., US, GB, US-CA)", show_default=True
)
@click.option(
    "--hours",
    type=click.Choice(["4", "24", "48", "168"], case_sensitive=False),
    default="24",
    help="Time period in hours",
    show_default=True,
)
@click.option(
    "--category",
    default="all",
    help="Category filter (e.g., sports, tech, health)",
    show_default=True,
)
@click.option(
    "--output",
    type=click.Choice(["csv", "json", "dataframe", "parquet", "dict"], case_sensitive=False),
    default="csv",
    help="Output format",
    show_default=True,
)
@click.option("--active-only", is_flag=True, help="Show only active/rising trends")
@click.option(
    "--sort",
    type=click.Choice(SORT_OPTIONS, case_sensitive=False),
    default="relevance",
    help="Sort order",
    show_default=True,
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./downloads",
    help="Output directory for files",
    show_default=True,
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress human-readable banners; print only the requested output (pipe-safe).",
)
@click.option(
    "--normalize",
    is_flag=True,
    help="Return the unified agent-friendly NormalizedEnvelope as JSON (ignores --output).",
)
@click.option(
    "--timeout",
    type=int,
    default=10,
    help="Page-load timeout in seconds.",
    show_default=True,
)
@click.option(
    "--max-retries",
    type=int,
    default=3,
    help="Scrape attempts on transient failure.",
    show_default=True,
)
def csv(
    geo: str,
    hours: str,
    category: str,
    output: str,
    active_only: bool,
    sort: str,
    output_dir: str,
    quiet: bool,
    normalize: bool,
    timeout: int,
    max_retries: int,
) -> None:
    """
    Download trends via CSV export (comprehensive, filtered).

    Examples:
        trendspyg csv --geo US
        trendspyg csv --geo US-CA --hours 168 --category sports
        trendspyg csv --geo GB --active-only --output json
    """
    if not quiet and not normalize:
        click.echo(f"Downloading CSV trends for {geo}...")
        click.echo(f"  Time period: {hours}h")
        click.echo(f"  Category: {category}")
        click.echo(f"  Active only: {active_only}")

    try:
        result = download_google_trends_csv(
            geo=geo,
            hours=int(hours),
            category=category,
            output_format=cast(Any, output),
            active_only=active_only,
            sort_by=sort,
            download_dir=output_dir,
            normalize=normalize,
            timeout=timeout,
            max_retries=max_retries,
        )

        if normalize:
            import json as _json

            click.echo(_json.dumps(result, indent=2, default=str))
            return

        result = cast(Any, result)
        if output in ("csv", "json", "parquet"):
            if quiet:
                click.echo(result)
            else:
                click.echo(f"\n[OK] Downloaded: {result}")
        elif output == "dict":
            if not quiet:
                click.echo(f"\nRetrieved {len(result)} trends")
            click.echo(result)
        elif output == "dataframe":
            if quiet:
                click.echo(result.to_string())
            else:
                click.echo(f"\nTop 10 Trends (Total: {len(result)}):\n")
                click.echo("=" * 100)

                # Show first 10 trends with details
                for i, (idx, row) in enumerate(result.head(10).iterrows(), 1):
                    click.echo(f"\n{i}. {row['Trends'].upper()}")
                    click.echo(f"   Search Volume: {row['Search volume']}")
                    if "Started" in row and row["Started"]:
                        click.echo(f"   Started: {row['Started']}")
                    if "Trend breakdown" in row and row["Trend breakdown"]:
                        breakdown = row["Trend breakdown"]
                        if len(str(breakdown)) > 100:
                            breakdown = str(breakdown)[:100] + "..."
                        click.echo(f"   Related: {breakdown}")
                    click.echo(f"   Explore: {row['Explore link']}")

                    if i < 10 and i < len(result):
                        click.echo("-" * 100)

                if len(result) > 10:
                    click.echo(f"\n... and {len(result) - 10} more trends")

                click.echo(f"\n[OK] Total: {len(result)} trends")

    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--keyword",
    "-k",
    "keywords",
    multiple=True,
    required=True,
    help='Search term to analyze (e.g. "bitcoin"). Repeat -k (2-5 times) to *compare* terms '
    "on one shared 0-100 scale.",
)
@click.option(
    "--geo", default="US", help="Country/region code (e.g., US, GB, US-CA)", show_default=True
)
@click.option(
    "--timeframe",
    default="today 12-m",
    help="Date range, e.g. 'today 12-m', 'today 5-y', 'now 7-d', 'all'",
    show_default=True,
)
@click.option(
    "--category", type=int, default=0, help="Google Trends category id (0 = all)", show_default=True
)
@click.option(
    "--output",
    type=click.Choice(["dict", "json", "csv", "dataframe"], case_sensitive=False),
    default="json",
    help="Output format for the interest-over-time series",
    show_default=True,
)
@click.option(
    "--full",
    is_flag=True,
    help="Output the full Explore envelope (interest + related queries + regions) as JSON.",
)
@click.option("--visible", is_flag=True, help="Run the browser in visible (non-headless) mode")
@click.option(
    "--quiet", "-q", is_flag=True, help="Suppress banners; print only the data (pipe-safe)."
)
@click.option(
    "--max-retries",
    type=int,
    default=10,
    help="Chart-load attempts past Google's soft-throttle.",
    show_default=True,
)
@click.option(
    "--retry-wait",
    type=float,
    default=8.0,
    help="Seconds to watch the chart per attempt. Worst case ~ max-retries * (retry-wait + 2s).",
    show_default=True,
)
def explore(
    keywords: tuple,
    geo: str,
    timeframe: str,
    category: int,
    output: str,
    full: bool,
    visible: bool,
    quiet: bool,
    max_retries: int,
    retry_wait: float,
) -> None:
    """
    Analyze a keyword over time (interest over time, related queries, regions).

    Pass -k more than once (2-5 terms) to *compare* keywords on one shared
    0-100 scale — the output is then the comparison envelope (values keyed by
    keyword + averages + per-region winners); --full is implied.

    Note: this drives a real browser against Google's Explore page and is
    rate-limit sensitive (~10-90s, may retry). Use it for analysis, not
    high-frequency polling — use `rss` for fast real-time checks.

    Examples:
        trendspyg explore --keyword bitcoin
        trendspyg explore -k "taylor swift" --timeframe "today 5-y" --output csv
        trendspyg explore -k bitcoin --full --quiet | jq .
        trendspyg explore -k bitcoin -k ethereum -k solana --quiet | jq .averages
    """
    if len(keywords) > 1:
        # Comparison mode: 2-5 keywords on one shared relative scale.
        if not quiet and not full:
            click.echo(f"Comparing {', '.join(keywords)} ({geo}, {timeframe})...")
        try:
            # [*keywords], not list(keywords) — the `list` click command shadows
            # the builtin in this module's namespace.
            result = download_google_trends_comparison(
                [*keywords],
                geo=geo,
                timeframe=timeframe,
                category=category,
                headless=not visible,
                output_format=cast(Any, output),
                max_retries=max_retries,
                retry_wait=retry_wait,
            )
            result = cast(Any, result)
            if output == "dataframe":
                click.echo(result.to_string())
            else:
                click.echo(result)
            if not quiet:
                click.echo("\n[OK] Success!")
        except Exception as e:
            click.echo(f"[ERROR] {e}", err=True)
            sys.exit(1)
        return

    keyword = keywords[0]
    if not quiet and not full:
        click.echo(f"Analyzing '{keyword}' ({geo}, {timeframe})...")

    try:
        if full:
            import json as _json

            env = download_google_trends_explore(
                keyword,
                geo=geo,
                timeframe=timeframe,
                category=category,
                headless=not visible,
                max_retries=max_retries,
                retry_wait=retry_wait,
            )
            click.echo(_json.dumps(env, indent=2, default=str))
            return

        result = download_google_trends_interest_over_time(
            keyword,
            geo=geo,
            timeframe=timeframe,
            category=category,
            headless=not visible,
            output_format=cast(Any, output),
            max_retries=max_retries,
            retry_wait=retry_wait,
        )

        result = cast(Any, result)
        if output == "dataframe":
            click.echo(result.to_string())
        else:
            click.echo(result)

        if not quiet:
            click.echo("\n[OK] Success!")

    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--geo", default="US", help="Country/region code (e.g., US, GB, US-CA)", show_default=True
)
@click.option("--interval", type=int, default=60, help="Seconds between polls", show_default=True)
@click.option(
    "--iterations",
    type=int,
    default=None,
    help="Number of polls before stopping (default: run until Ctrl-C)",
)
@click.option(
    "--min-volume",
    type=int,
    default=None,
    help="Only report changes at/above this traffic_min",
)
@click.option(
    "--events",
    default=None,
    help="Comma-separated events to report: new,dropped,volume_up,volume_down,rank_change",
)
@click.option(
    "-k",
    "--keyword",
    "keywords",
    multiple=True,
    help="Watchlist term (repeatable); case-insensitive substring match",
)
@click.option(
    "--webhook", default=None, help="POST each change as JSON to this URL (fire-and-forget)"
)
@click.option(
    "--quiet", "-q", is_flag=True, help="Suppress the startup banner; stream only NDJSON."
)
def watch(
    geo: str,
    interval: int,
    iterations: int,
    min_volume: int,
    events: str,
    keywords: tuple,
    webhook: str,
    quiet: bool,
) -> None:
    """
    Monitor trends in real time; stream each change as NDJSON (one JSON per line).

    Built on the fast RSS path, so it is safe for continuous polling (unlike the
    `csv` and `explore` paths). The first poll is the baseline; each later poll
    is diffed against it. stdout carries only NDJSON — pipe it into `jq` or a
    file.

    Examples:
        trendspyg watch --geo US --interval 60
        trendspyg watch --geo US --events new,volume_up --min-volume 50000
        trendspyg watch -k bitcoin -k ethereum --webhook https://example.com/hook
        trendspyg watch --geo US --iterations 5 --quiet | jq .
    """
    import json as _json

    from .monitor import watch_google_trends_rss

    event_list = [e.strip() for e in events.split(",") if e.strip()] if events else None

    if not quiet:
        click.echo(
            f"[watch] Monitoring RSS trends for {geo} every {interval}s. "
            "Streaming NDJSON; Ctrl-C to stop.",
            err=True,
        )

    try:
        for change in watch_google_trends_rss(
            geo=geo,
            interval=interval,
            iterations=iterations,
            min_volume=min_volume,
            events=event_list,
            keywords=[*keywords] or None,
            webhook=webhook,
        ):
            click.echo(_json.dumps(change, default=str))
    except KeyboardInterrupt:
        if not quiet:
            click.echo("\n[watch] Stopped.", err=True)
    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--type",
    "list_type",
    type=click.Choice(["countries", "states", "categories", "hours"], case_sensitive=False),
    required=True,
    help="Type of list to show",
)
def list(list_type: str) -> None:
    """
    List available options.

    Examples:
        trendspyg list --type countries
        trendspyg list --type states
        trendspyg list --type categories
    """
    if list_type == "countries":
        click.echo(f"\nAvailable Countries ({len(COUNTRIES)}):\n")
        for code, name in sorted(COUNTRIES.items()):
            click.echo(f"  {code:4} - {name}")

    elif list_type == "states":
        click.echo(f"\nAvailable US States ({len(US_STATES)}):\n")
        for code, name in sorted(US_STATES.items()):
            click.echo(f"  {code:8} - {name}")

    elif list_type == "categories":
        click.echo(f"\nAvailable Categories ({len(CATEGORIES)}):\n")
        for cat in sorted(CATEGORIES.keys()):
            click.echo(f"  {cat}")

    elif list_type == "hours":
        click.echo("\nAvailable Time Periods:\n")
        for hours, label in TIME_PERIODS.items():
            click.echo(f"  {hours:3} hours - {label}")


@cli.command()
def info() -> None:
    """Show package information and statistics."""
    click.echo("\n" + "=" * 60)
    click.echo("trendspyg - Google Trends Data Downloader")
    click.echo("=" * 60)
    click.echo(f"\nVersion: {__version__}")
    click.echo("License: MIT")
    click.echo("Homepage: https://github.com/flack0x/trendspyg")
    click.echo("\nSupported Options:")
    click.echo(f"  Countries:  {len(COUNTRIES)}")
    click.echo(f"  US States:  {len(US_STATES)}")
    click.echo(f"  Categories: {len(CATEGORIES)}")
    click.echo(f"  Time Periods: {len(TIME_PERIODS)}")
    click.echo(f"  Sort Options: {len(SORT_OPTIONS)}")
    click.echo("\nData Sources:")
    click.echo("  RSS:      Fast (typically 0.2-2s), rich media, ~10-20 current trends")
    click.echo("  CSV:      Comprehensive (10s), filtered, ~480+ current trends")
    click.echo("  Explore:  Keyword analysis over time (interest, related, regions)")
    click.echo("  Watch:    Continuous RSS monitoring (trendspyg watch)")
    click.echo("\n" + "=" * 60)


def main() -> None:
    """Main entry point for CLI."""
    _configure_stdout_encoding()
    cli()


if __name__ == "__main__":
    main()
