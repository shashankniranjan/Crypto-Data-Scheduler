# Requirements Addendum: Sources, Support Matrix, Schema, and Incremental Ingestion

## A. Source Strategy (Industry Standard)

### A1. Three ingestion temperature bands

| Band | Time range | Primary source | Fallback | Purpose |
| --- | --- | --- | --- | --- |
| Hot | now -> last ~6 hours | WebSocket + REST | REST only | Poll every minute, low latency |
| Warm | last ~7 days | REST | Vision when appears | Fill recent gaps; Vision may lag |
| Cold | older history | Binance Vision daily zips | REST (repair only) | Bulk backfill efficiently |

Hard rule: polling every minute is not achievable using Vision-only (daily archives appear after the day completes). Hot/Warm must use REST/WebSocket.

## B. Data Source Locations (Exact)

### B1. Binance Vision (historical bulk)

Base URL (USDT-M futures, daily):

`https://data.binance.vision/data/futures/um/daily/`

Streams available:

- `aggTrades/`
- `bookDepth/`
- `bookTicker/`
- `indexPriceKlines/`
- `klines/`
- `markPriceKlines/`
- `metrics/`
- `premiumIndexKlines/`
- `trades/`

### B1.1 Standard Vision path patterns (daily zips)

| Stream | Vision path pattern (daily) | File name pattern |
| --- | --- | --- |
| Klines (1m) | `klines/{SYMBOL}/1m/` | `{SYMBOL}-1m-{YYYY-MM-DD}.zip` |
| AggTrades | `aggTrades/{SYMBOL}/` | `{SYMBOL}-aggTrades-{YYYY-MM-DD}.zip` |
| BookTicker | `bookTicker/{SYMBOL}/` | `{SYMBOL}-bookTicker-{YYYY-MM-DD}.zip` |
| BookDepth | `bookDepth/{SYMBOL}/` | `{SYMBOL}-bookDepth-{YYYY-MM-DD}.zip` |
| Mark Price Klines (1m) | `markPriceKlines/{SYMBOL}/1m/` | `{SYMBOL}-markPriceKlines-1m-{YYYY-MM-DD}.zip` |
| Index Price Klines (1m) | `indexPriceKlines/{SYMBOL}/1m/` | `{SYMBOL}-indexPriceKlines-1m-{YYYY-MM-DD}.zip` |
| Premium Index Klines (1m) | `premiumIndexKlines/{SYMBOL}/1m/` | `{SYMBOL}-premiumIndexKlines-1m-{YYYY-MM-DD}.zip` |
| Metrics | `metrics/{SYMBOL}/` | `{SYMBOL}-metrics-{YYYY-MM-DD}.zip` |
| Trades | `trades/{SYMBOL}/` | `{SYMBOL}-trades-{YYYY-MM-DD}.zip` |

Hard rule: if the expected zip for a day is missing, pipeline must record a missing-source event and fall back according to band rules (Hot/Warm via REST; Cold via retry/backfill queue).

### B2. Binance REST (hot/warm backfill + gaps)

Base URL:

`https://fapi.binance.com`

| What | Endpoint | Use |
| --- | --- | --- |
| 1m klines | `/fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime=...&endTime=...` | Hot/Warm OHLC |
| aggTrades | `/fapi/v1/aggTrades?symbol=BTCUSDT&startTime=...&endTime=...&limit=1000` | Hot/Warm tick -> 1m metrics |
| bookTicker snapshot | `/fapi/v1/ticker/bookTicker?symbol=BTCUSDT` | Hot best bid/ask snapshot polling |
| premium/mark/index snapshot | `/fapi/v1/premiumIndex?symbol=BTCUSDT` | Hot mark/index/premium + predicted funding + next funding time |
| open interest | `/fapi/v1/openInterest?symbol=BTCUSDT` | Hot OI |
| funding history | `/fapi/v1/fundingRate?symbol=BTCUSDT&limit=...` | Historical funding events |

REST requirements:

- Use REST for gaps and recent minutes.
- Enforce rate limits (bounded concurrency + backoff + jitter).
- Replace/confirm REST with Vision when Vision exists (cold truth).

Note on predicted funding / next funding time:

- `/fapi/v1/fundingRate` returns settled funding events (`fundingTime`, `fundingRate`, `markPrice`).
- Real-time predicted funding + next funding time should come from `premiumIndex`/mark-price live data and be treated as live-only unless proven in Vision.

### B3. Binance WebSocket (true live microstructure)

Base URL:

`wss://fstream.binance.com/ws`

| Stream | Example | Used for |
| --- | --- | --- |
| `@depth@100ms` or `@depth` | `btcusdt@depth@100ms` | `update_id_start/end`, `price_impact_100k` from L2 |
| `@markPrice@1s` | `btcusdt@markPrice@1s` | predicted funding + next funding time (live) |
| `@aggTrade` | `btcusdt@aggTrade` | tick stream for intra-minute features |
| local arrival timestamps | receiver-side capture | `arrival_time`, `latency_network` |

Hard rule: WebSocket is optional initially. If not implemented, live-only columns must be `NULL` by contract.

## C. Support Matrix (Mandatory)

### C1. Support classes

| Class | Meaning | Required in dataset? |
| --- | --- | --- |
| `HARD_REQUIRED` | Must exist for every stored minute | Yes |
| `BACKFILL_AVAILABLE` | Can be computed historically from Vision/REST | Yes |
| `LIVE_ONLY` | Only available if collectors run live | Yes, but NULL historically |
| `OPTIONAL` | Nice-to-have, may be missing | Yes, may be NULL |

### C2. Support rules

- If a `HARD_REQUIRED` field is missing for a minute, that minute is not committed and watermark must not advance beyond it.
- If a `BACKFILL_AVAILABLE` field is missing due to source-file gap, apply fill policy and log warning; still commit if `HARD_REQUIRED` fields are satisfied.
- If a `LIVE_ONLY` field collector is not running, always store `NULL`; still commit.

## D. Canonical Metric Definitions (Locked Formulas)

### D1. Minute bucketing

- `timestamp` is UTC minute start.
- Event belongs to bucket if `timestamp <= event_time < timestamp + 60_000 ms`.

### D2. VWAP

`vwap_1m = SUM(price * qty) / SUM(qty)` using aggTrades in the bucket.

If `SUM(qty) = 0`, set `vwap_1m = close`.

### D3. AggTrade direction

- `isBuyerMaker == False` -> taker buy
- `isBuyerMaker == True` -> taker sell

### D4. Realized volatility

Order prices by `transact_time`:

`r_i = ln(p_i / p_{i-1})`

`realized_vol_1m = sqrt(SUM(r_i^2))`

If fewer than two ticks, set to `0`.

### D5. Microprice

From last bookTicker snapshot in minute:

`micro_price_close = (bid_price*ask_qty + ask_price*bid_qty) / (bid_qty + ask_qty)`

If denominator is zero, set `NULL`.

### D6. Whale / retail thresholds

Per trade notional = `price * qty`.

- Whale: `>= 100_000 USDT`
- Retail: `<= 1_000 USDT`

### D7. Forward-fill policy

- Only for slow-moving snapshot fields (OI, ratios, funding fields).
- `max_ffill_minutes` default `60`; beyond that set `NULL` and warn.

## E. Incremental Polling, Watermark, Idempotency (Poll Every Minute)

### E1. State store (SQLite, required locally)

Required tables:

- `watermark(symbol, last_complete_minute_utc, updated_at_utc)`
- `partitions(symbol, day, hour, path, row_count, min_ts, max_ts, schema_hash, content_hash, status, committed_at_utc)`

### E2. Poll loop (every 60 seconds)

Each tick:

1. `target_horizon = floor_to_minute(now_utc - safety_lag_minutes)` with default lag `3`.
2. Missing range: `(last_complete_minute_utc + 1) .. target_horizon`.
3. For each overlapping hour partition:
   - Fetch required sources by Hot/Warm/Cold strategy.
   - Build minute dataframe for that hour.
   - Validate and commit atomically.
4. Advance watermark only after earliest missing minute is present and committed.

### E3. Atomic commit protocol

1. Write temp: `.../.tmp/{uuid}.parquet`
2. Validate schema hash, uniqueness, and DQ checks.
3. Atomic rename to final path.
4. Mark partition `COMMITTED` in SQLite.
5. Advance watermark.

### E4. Output partitioning (recommended for polling)

Use hourly partitions:

`.../symbol=BTCUSDT/year=YYYY/month=MM/day=DD/hour=HH/part.parquet`

## F. Schema (58 Columns)

Primary key: `(symbol, timestamp)` (symbol implied by partition).

| Column | Type | Source | SupportClass | Fill policy |
| --- | --- | --- | --- | --- |
| event_time | BigInt | WebSocket events | LIVE_ONLY | NULL if not collected |
| transact_time | BigInt | aggTrades / mark price stream | BACKFILL_AVAILABLE | NULL if no trade |
| arrival_time | BigInt | local capture | LIVE_ONLY | NULL historically |
| latency_engine | Int | derived | LIVE_ONLY | NULL if missing inputs |
| latency_network | Int | derived | LIVE_ONLY | NULL if missing inputs |
| update_id_start | BigInt | depthUpdate | LIVE_ONLY | NULL if no depth |
| update_id_end | BigInt | depthUpdate | LIVE_ONLY | NULL if no depth |
| timestamp | Datetime | klines | HARD_REQUIRED | no nulls |
| open | Float | klines | HARD_REQUIRED | no nulls |
| high | Float | klines | HARD_REQUIRED | no nulls |
| low | Float | klines | HARD_REQUIRED | no nulls |
| close | Float | klines | HARD_REQUIRED | no nulls |
| vwap_1m | Float | aggTrades | BACKFILL_AVAILABLE | close if no qty |
| micro_price_close | Float | bookTicker | BACKFILL_AVAILABLE | NULL if no snapshot |
| volume_btc | Float | klines | HARD_REQUIRED | 0 allowed |
| volume_usdt | Float | klines | HARD_REQUIRED | 0 allowed |
| trade_count | Int | klines | HARD_REQUIRED | 0 allowed |
| avg_trade_size_btc | Float | derived | BACKFILL_AVAILABLE | 0 if trade_count=0 |
| max_trade_size_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if no trades |
| taker_buy_vol_btc | Float | klines or aggTrades | BACKFILL_AVAILABLE | 0 if none |
| taker_buy_vol_usdt | Float | klines or aggTrades | BACKFILL_AVAILABLE | 0 if none |
| net_taker_vol_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| count_buy_trades | Int | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| count_sell_trades | Int | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| taker_buy_ratio | Float | derived | BACKFILL_AVAILABLE | NULL if denom=0 |
| vol_buy_whale_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| vol_sell_whale_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| vol_buy_retail_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| vol_sell_retail_btc | Float | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| whale_trade_count | Int | aggTrades | BACKFILL_AVAILABLE | 0 if none |
| realized_vol_1m | Float | aggTrades | BACKFILL_AVAILABLE | 0 if <2 ticks |
| liq_long_vol_usdt | Float | forceOrder WS/REST | LIVE_ONLY | NULL unless collected |
| liq_short_vol_usdt | Float | forceOrder WS/REST | LIVE_ONLY | NULL unless collected |
| liq_long_count | Int | forceOrder WS/REST | LIVE_ONLY | NULL unless collected |
| liq_short_count | Int | forceOrder WS/REST | LIVE_ONLY | NULL unless collected |
| liq_avg_fill_price | Float | forceOrder | LIVE_ONLY | NULL unless collected |
| liq_unfilled_ratio | Float | forceOrder | LIVE_ONLY | NULL unless collected |
| avg_spread_usdt | Float | bookTicker | BACKFILL_AVAILABLE | ffill within limit |
| bid_ask_imbalance | Float | bookTicker | BACKFILL_AVAILABLE | ffill within limit |
| avg_bid_depth | Float | bookTicker | BACKFILL_AVAILABLE | ffill within limit |
| avg_ask_depth | Float | bookTicker | BACKFILL_AVAILABLE | ffill within limit |
| spread_pct | Float | bookTicker | BACKFILL_AVAILABLE | ffill within limit |
| price_impact_100k | Float | depth book | LIVE_ONLY | NULL unless collected |
| oi_contracts | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| oi_value_usdt | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| top_trader_ls_ratio_acct | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| global_ls_ratio_acct | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| ls_ratio_divergence | Float | derived | BACKFILL_AVAILABLE | ffill within limit |
| top_trader_long_pct | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| top_trader_short_pct | Float | REST/metrics | BACKFILL_AVAILABLE | ffill within limit |
| mark_price_open | Float | markPriceKlines | HARD_REQUIRED | no nulls for stored minutes |
| mark_price_close | Float | markPriceKlines | HARD_REQUIRED | no nulls |
| index_price_open | Float | indexPriceKlines | HARD_REQUIRED | no nulls |
| index_price_close | Float | indexPriceKlines | HARD_REQUIRED | no nulls |
| premium_index | Float | premium/index/mark | BACKFILL_AVAILABLE | computed; no nulls if inputs available |
| funding_rate | Float | fundingRate REST / premiumIndex | BACKFILL_AVAILABLE | ffill; settles every 8h |
| predicted_funding | Float | WS markPrice / premiumIndex REST | LIVE_ONLY (unless proven in Vision) | NULL historically |
| next_funding_time | BigInt | WS markPrice / premiumIndex REST | LIVE_ONLY (unless proven in Vision) | NULL historically |

Developer note: fields marked as `REST/metrics` depend on whether Vision `metrics/` contains those values at usable cadence. If absent, use REST or `NULL` by SupportClass policy; always log source provenance per partition.

## G. Storage Layout (Local Now, Cloud Later)

### G1. Local filesystem layout

`{root}/futures/um/minute/symbol=BTCUSDT/year=YYYY/month=MM/day=DD/hour=HH/part.parquet`

### G2. Cloud migration

Same layout is cloud-compatible (S3/GCS), with implementation swaps:

- local filesystem ops -> object store client
- atomic rename -> write-temp plus manifest-pointer pattern
- scheduler can remain local daemon/cron initially; Airflow optional at larger scale

## H. Developer Deliverables (Minimum)

- Vision URL builder with file existence checks
- REST collectors for Hot/Warm windows
- Optional WebSocket collectors for live-only fields
- Transform engine (Polars recommended)
- SQLite state store (`watermark`, `partitions`)
- Idempotent writer (atomic commit + schema hash)
- DQ checks + structured logging

Recommended hardening step: open one `metrics/{SYMBOL}-metrics-{DATE}.zip` and enumerate columns. This determines whether sentiment/OI fields are truly Vision-backfillable or REST-only.

## I. Frequency Normalization Classification

| Category | Streams / fields | Native resolution | How it becomes 1m in the lake |
| --- | --- | --- | --- |
| Already 1m bars | `klines 1m`, `markPriceKlines 1m`, `indexPriceKlines 1m`, `premiumIndexKlines 1m` | 1m | Direct join on minute timestamp |
| Tick/event streams | `aggTrades`, `trades` | per trade | Bucket by minute and aggregate (VWAP, realized vol, whale metrics, buy/sell flow) |
| Snapshots | `bookTicker`, `bookDepth` | irregular or high-frequency | Aggregate per minute with locked rule (last-in-minute or mean/time-weighted mean) |
| Slow/stepwise series | `funding_rate`, sentiment ratios, OI snapshots | 8h or irregular | Time join + bounded forward-fill |
| Live-only infra metrics | `arrival_time`, `latency_*`, `update_id_*`, `predicted_funding`, `next_funding_time`, `price_impact_100k` | event-driven | Aggregate/last-value per minute if live collectors run; else NULL |

Definition of 1m TF in this system:

- Output table is one row per minute.
- Mixed-frequency inputs are normalized into that grid via:
  - resample/aggregate (ticks/snapshots -> 1m)
  - bounded forward-fill (slow/irregular series -> 1m)
  - `NULL` for unsupported historical live-only fields
