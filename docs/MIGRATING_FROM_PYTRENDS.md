# Migrating from pytrends

pytrends was archived in April 2025, so it receives no fixes. Checked from one
machine on 2026-10-02, pytrends 4.9.2's keyword analysis (`interest_over_time`,
`interest_by_region`, `related_queries`) still answered, but
`trending_searches`, `today_searches`, `realtime_trending_searches` and
`top_charts` failed with HTTP 404 because Google no longer serves those
endpoints. Its issue tracker also records waves of HTTP 429
(`TooManyRequestsError`) when Google refuses its direct requests.

Since 1.9.0, trendspyg ships a **pytrends-compatible `TrendReq`**: your
existing code runs after changing its imports. What you gain: the trending
calls work again, the code is maintained, and keyword analysis asks Google
directly (as fast as pytrends while Google allows it) with a real browser
page as the fallback when Google refuses. What it costs: when the fallback is
needed, a payload's first call takes roughly 10-40 seconds instead of a few.

```bash
pip install "trendspyg[analysis]"   # pandas, as pytrends needed
```

```python
# from pytrends.request import TrendReq          # before
from trendspyg.compat.request import TrendReq     # after

pytrends = TrendReq(hl="en-US", tz=360)
pytrends.build_payload(["coffee"], cat=0, timeframe="today 5-y", geo="", gprop="")

pytrends.interest_over_time()        # same DataFrame: date index, one column per keyword, isPartial
pytrends.interest_by_region(resolution="COUNTRY", inc_low_vol=True, inc_geo_code=False)
pytrends.related_queries()           # {"coffee": {"top": DataFrame, "rising": DataFrame}}
```

Replace `pytrends` with `trendspyg.compat` in every import: `pytrends.request`
becomes `trendspyg.compat.request`, and `pytrends.exceptions` becomes
`trendspyg.compat.exceptions`. `from trendspyg.compat import TrendReq` also works.

## How it is different underneath

pytrends called Google's internal endpoints directly; when Google refuses
those requests (HTTP 429) it has nothing to fall back on. `trendspyg.compat`
makes the same direct requests first (`engine="auto"`, the default) and, if
Google refuses, opens the real Explore page in Chrome and reads the data the
page itself loads.

- **The first data call after `build_payload` fetches everything the payload
  can give**: interest over time, related queries (for every compared
  keyword) and every supported region view. Directly that took 1-7 seconds
  in our measurements; through the browser, roughly 10-40 seconds. Later
  calls on the same payload return from memory in milliseconds.
- **Google limits a machine.** Measured from one machine: direct requests were
  refused after roughly a hundred in half an hour, for about five minutes at
  first; fresh browser sessions are refused after roughly 8-10 in a short
  burst; after heavier use both were refused. Then every call raises
  `TooManyRequestsError` until the machine cools down (tens of minutes at
  least). Do not retry in a loop.
- `TrendReq(engine="browser")` always uses the browser; `engine="http"` never
  starts Chrome and raises `TooManyRequestsError` when Google refuses.
- **Use the disk cache and the cookie jar for anything you run repeatedly:**

  ```python
  pytrends = TrendReq(hl="en-US", tz=360, cache="disk", cookies="disk")
  ```

  `cache="disk"` answers an identical recent payload without a browser
  (fresh for 1 hour on `now *` timeframes, 24 hours otherwise).
  `cookies="disk"` keeps Google's session cookies in a small file so later
  sessions arrive as a returning visitor, which Google serves when it is
  refusing new ones. Both are off by default because they write to disk.
- Chrome is needed only for the fallback (or `engine="browser"`). Selenium
  downloads its driver automatically.

## Method by method

| pytrends call | trendspyg.compat |
|---|---|
| `build_payload(kw_list, cat, timeframe, geo, gprop)` | Same arguments, validated before any browser starts. 1-5 keywords. |
| `interest_over_time()` | Same DataFrame (`date` index, int column per keyword, `isPartial`). |
| `interest_by_region(resolution, inc_low_vol, inc_geo_code)` | Same DataFrame (sorted `geoName` index, optional `geoCode`). `inc_low_vol=True` and `resolution="DMA"` (US metro areas, `geo="US"`) work. See the differences below. |
| `related_queries()` | Same dict of `top` / `rising` DataFrames (`query`, `value`), `None` when Google lists none. |
| `related_topics()` | Returns `None` tables and warns: Google serves this widget empty to automated sessions. |
| `suggestions(keyword)` | Same list of `{mid, title, type}`; uses `hl`. No browser. |
| `categories()` | Same category tree; uses `hl`. No browser. |
| `trending_searches(pn="united_states")` | Same one-column DataFrame, from Google's Trending Now feed. `pn` accepts pytrends' names or codes. |
| `today_searches(pn="US")` | A Series of trending searches (`query`), from the Trending Now feed. |
| `realtime_trending_searches(pn="US", cat="all", count=300)` | `title` and `entityNames` columns from the Trending Now feed; `entityNames` holds the search itself. `cat` must be `"all"`. |
| `top_charts(...)` | `NotImplementedError`: Google's Year in Search endpoint answers HTTP 404. |
| `multirange_interest_over_time()`, a list `timeframe` | `NotImplementedError`: call `build_payload` once per range. |
| `get_historical_interest(...)` | `NotImplementedError`, as in pytrends, which removed it for incorrectness. |

## Differences to know

- **Regions with no data are left out.** pytrends listed them with a value of
  0. Sorting and taking the top rows gives the same answer.
- **`resolution="CITY"` raises `NotImplementedError`.** Google refused city
  data for the US when tested, and its worldwide city rows carry coordinates
  instead of region codes. `"DMA"` works for `geo="US"`. A worldwide payload
  (`geo=""`) serves countries only, as before.
- **`proxies=` is refused** with an error rather than ignored, because a
  browser fallback would not use your proxies. To use a proxy, set the
  `HTTPS_PROXY` environment variable and pass `engine="http"`: direct requests
  follow it and no browser starts. Verified 2026-10-02 through a rotating
  residential proxy (a new address per request).
- **`tz`, `timeout`, `retries`, `backoff_factor` and `requests_args` are
  accepted but not applied.** The browser reports this machine's timezone;
  trendspyg uses its own timeouts and reload ladder. `hl` applies to
  `suggestions()` and `categories()`; Explore data comes back in English.
- **A keyword containing a comma is refused**, because the Explore page's
  address uses commas to separate keywords.
- **`geo` must be `""` (worldwide), one of trendspyg's 125 countries, or a US
  state** such as `"US-CA"`. Other sub-region codes are not accepted yet.
- **`related_queries()` on a 2-5 keyword payload** comes with the direct
  answer. After a browser fallback it runs one more browser session per
  keyword, because Google's comparison page does not include them.
- **Exceptions:** `TooManyRequestsError` and `ResponseError` keep their
  pytrends names. Both are also trendspyg exceptions (`TooManyRequestsError`
  is a `RateLimitError`). Their `response` attribute is `None`. A missing
  Chrome raises trendspyg's `BrowserError`; a bad argument raises
  `InvalidParameterError`.

## Checked against pytrends itself

The compatibility tests feed the same raw Google data to pytrends 4.9.2 and to
`trendspyg.compat` and compare the DataFrames, including column order, index
and dtypes, under pandas 2 and pandas 3. The only intended difference is the
omitted no-data regions. A live run of pytrends' README example (`"Blockchain"`,
worldwide, five years) on 2026-10-02 returned 262 weekly points, 218 countries
with `inc_low_vol=True` and 25 top and 25 rising related queries from one
16-second browser session. That night pytrends itself, from the same machine,
answered 12 of 12 keyword-analysis requests (0.6-4.4 seconds each) and failed
its four trending calls with HTTP 404. Direct requests made the way the
`"auto"` engine makes them answered the same README payload in 3 seconds with
the same dates and countries, values within 4 points of the browser's.

Rising related queries deserve care whichever library fetches them: see
[Interpreting data](INTERPRETING_DATA.md#related-queries-are-leads-not-facts).

## Moving to the native API (optional)

The native functions return JSON-safe data, record history, and compare
keywords in one call:

```python
from trendspyg import download_google_trends_explore, download_google_trends_comparison

env = download_google_trends_explore("coffee", geo="US", cache="disk", cookies="disk")
cmp = download_google_trends_comparison(["coffee", "tea"], geo="US")
```

See the [API reference](API.md) and
[Interpreting data](INTERPRETING_DATA.md).
