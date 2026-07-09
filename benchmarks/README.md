# trendspyg benchmarks

Reproducible performance numbers for the library. Run them yourself:

```bash
python benchmarks/run_benchmarks.py                 # offline only — safe anywhere, no network
python benchmarks/run_benchmarks.py --live          # + live RSS (fresh + cache hit)
python benchmarks/run_benchmarks.py --live-csv      # + live CSV export (Chrome, ~10-15s per clean run)
python benchmarks/run_benchmarks.py --live-explore  # + live Explore (Chrome, 10-90s)
```

The offline suite measures the library's own overhead on synthetic-but-realistic
inputs (a 20-item RSS feed — the size Google actually serves). The live flags hit
Google for end-to-end timings. **Live numbers are network-dominated**: your
latency to Google's edge, and whether Google soft-throttles the request, matter
far more than anything in this library.

These are *not* a CI gate — live-network timing on shared runners would fail
randomly. They are measured on a real machine and re-recorded per release.

## Results — v1.0.0

Measured 2026-07-09 · Windows 11 · Python 3.13 · residential connection (Beirut) ·
Chrome headless for the browser paths.

### Library overhead (offline, median per call)

| Operation | Median |
|---|---|
| Parse a 20-trend RSS feed (images + articles) | ~620 µs |
| `normalize=True` envelope for 20 trends | ~38 µs |
| `diff_trends` — 20 vs 20 snapshot diff | ~20 µs |
| `filter_changes` — 23 changes, all filters on | ~3 µs |

The library adds well under a millisecond to any request. Everything else is network.

### End-to-end (live, this machine)

| Path | Result |
|---|---|
| RSS fresh (`cache=False`), 5 runs | median **1.4 s** (1.2–1.7 s) |
| RSS cache hit | **1.5 µs** (~1,000,000× the fresh call) |
| CSV export (Chrome), clean run | **12.4 s** |
| CSV export, immediate re-run (soft-throttled) | 84.4 s — retries recovered it |
| Explore interest over time (Chrome), 1 run | **34.0 s** |

### Honest notes

- **RSS latency is your network, not the library.** Historical measurements on
  low-latency links have seen ~0.2 s; this run's 1.4 s median reflects a
  high-RTT connection. The parse itself costs ~0.6 ms.
- **Back-to-back browser runs get throttled.** The 84 s CSV re-run immediately
  followed the 12 s clean run — Google soft-throttled and the built-in retries
  worked through it. Don't poll the browser paths; that's what the RSS path
  and its cache are for.
- **Explore is the slowest and most variable path** (10–90 s by design — it
  retries past Google's transient throttle). Tune with `max_retries` /
  `retry_wait` if you'd rather fail fast.
