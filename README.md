# TraderResearch

TraderResearch is a personal, non-commercial Python research framework for asking whether
permitted public social-media discussion about listed companies has measurable predictive
value for later market-price movement. It extracts stock mentions, measures deterministic
sentiment and discussion velocity, classifies event types, evaluates sources and authors,
calculates benchmark-adjusted forward returns, and produces reproducible research scores.

The current release runs end to end with bundled synthetic content. It neither needs nor
uses Reddit or brokerage credentials for basic research commands.

> TraderResearch is research software for analyzing public market-related discussion and
> simulated paper-trading signals.
>
> It does not provide investment advice.
>
> Live-money trading is not supported.
>
> Past or simulated performance does not imply future results.

## Safety and compliance boundaries

TraderResearch is **paper trading only**. The configuration and broker adapters reject any
environment other than `paper`, reject the standard live TWS port, support stocks only,
allow long positions only, and expose limit orders only. No command enables live trading.
Risk controls use the configured research capital rather than the nominal balance of a
broker paper account.

TraderResearch does not scrape Reddit webpages.

Reddit integration is designed for approved Reddit Data API access only.

The project does not post, comment, vote, send messages, or moderate Reddit.

Reddit content is not used to train or fine-tune AI/ML models.

The present Reddit API adapter is an intentionally non-operational boundary until approved
access and applicable terms are confirmed. Only the bundled, entirely fabricated sample
collector works by default. The architecture contains no Reddit account automation or
write operations. Before activating collection, review the current
[Reddit Data API Terms](https://redditinc.com/policies/data-api-terms) and
[Developer Terms](https://redditinc.com/policies/developer-terms); access, retention, deletion,
attribution, and publication rules may change.

## Architecture

The package keeps collection, analysis, market data, persistence, and execution separate:

```text
permitted collector -> social records -> extraction/classification -> research signals
                                              |                         |
symbol master + benchmark mapping ------------+                         v
                                                        forward-return evaluation
                                                                     |
                                                                     v
                                             source/author contextual scoring

explicit paper-run -> current market snapshot -> hard risk controls -> paper broker only
```

- `reddit`: a read-only protocol, bundled synthetic collector, and approved-API boundary.
- `market`: broad symbol-master, price-provider, and country/sector benchmark protocols.
- `analysis`: deterministic extraction, sentiment, events, velocity, manipulation flags,
  point-in-time signals, forward returns, and confidence-adjusted scoring.
- `storage`: SQLAlchemy schema and repositories. SQLite is the initial engine; domain logic
  is isolated so a PostgreSQL-backed repository can be added later.
- `trading`: paper broker protocol, optional official IBKR adapter, mock client, risk gate,
  order reconciliation, and structured decision audit records.

The schema includes `social_content`, `ticker_mentions`, `sources`, `authors`, `symbols`,
`signals`, `market_snapshots`, `forward_returns`, `paper_orders`, `paper_fills`,
`source_performance`, `author_performance`, and `strategy_runs`.

## Requirements and installation

- Python 3.12 or later
- SQLite (included with standard Python distributions)
- Optional: TWS or IB Gateway and the IBKR API package for `paper-status`
- Optional development tools: pytest, Ruff, mypy, pre-commit, and gitleaks

Create an isolated environment and install the project:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For tests and repository checks:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
```

Runtime SQLite files default to the operating system's per-user application-data location,
outside this repository. `TRADERRESEARCH_DATA_DIR` can point to another external directory.
Do not point it at the repository. Local databases, logs, `.env` files, and credentials are
ignored by Git.

## Synthetic quick start

Run these in order:

```bash
traderresearch ingest-sample
traderresearch analyze
traderresearch leaderboard
traderresearch signals
```

Additional read-only views are available:

```bash
traderresearch authors
traderresearch evaluate
traderresearch paper-status --mock
```

`ingest-sample` is idempotent. `analyze` deterministically rebuilds derived rows, source
performance, author-by-context performance, and synthetic forward returns. The synthetic
returns exist only to exercise the research machinery; they say nothing about actual market
performance.

Use `traderresearch --help` or `traderresearch COMMAND --help` for details. Global options,
including `--config`, precede the command.

## Configuration

The examples in `config/` define source scoring, signal weights, research capital, paper
connectivity, tradeability filters, and hard paper-risk limits. Load one with:

```bash
traderresearch --config config/sources.example.yaml analyze
```

YAML values are overridden by explicitly set environment variables. TraderResearch does not
automatically load `.env`, which reduces the chance of accidentally treating a repository
file as a secret store. `.env.example` contains placeholders only.

### Approved Reddit Data API access

After access is approved, supply credentials through a secure environment or secret manager:

```text
REDDIT_CLIENT_ID=REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET=REDDIT_CLIENT_SECRET
REDDIT_USER_AGENT=TraderResearch/0.1
```

Set `reddit.mode` to `api` only when approved credentials and a compliant read-only adapter
are available. API mode validates the three values; this release then stops with a clear
message because network collection has not yet been activated. Never commit the values or a
populated `.env` file.

Only collect fields required for the research question. `author_identifier` is deliberately
treated as an opaque identifier, allowing a future ingestion boundary to hash or pseudonymize
it before storage.

### IBKR paper status

Install the optional official API dependency:

```bash
python -m pip install -e '.[ibkr]'
```

Start TWS in **paper mode**, enable API connections, and retain its paper API default in the
example configuration:

```text
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
IBKR_ENVIRONMENT=paper
IBKR_LIVE_TRADING_ENABLED=false
```

Then run:

```bash
traderresearch paper-status
```

This command connects read-only, reports connectivity plus position/open-order counts, masks
or omits account identifiers, and does not submit an order. It intentionally does not print
account summaries, balances, buying power, or account numbers. The explicit `paper-run`
workflow is also submission-disabled by default and currently stops before submission until
a point-in-time market-data adapter is configured.

IB Gateway normally uses a different paper port. If using it, consult the current
[official IBKR setup documentation](https://ibkrcampus.com/campus/trading-lessons/installing-configuring-tws-for-the-api/)
and configure only its verified paper port; known live defaults are rejected. Install the
latest official TWS API package from IBKR when the convenience PyPI build is not current.

## Research methodology

### Point-in-time integrity and look-ahead bias

Each stage preserves the relevant clock:

- content creation and retrieval;
- signal generation;
- market-price observation;
- paper-order submission; and
- fill time.

A signal can use only observations with an availability timestamp at or before its generation
time. The synthetic pipeline enforces this when computing rolling source and author history:
later forward returns do not influence earlier scores. A production market-data adapter must
apply the same rule to price, volume, news confirmation, liquidity, and benchmark data.

Avoid revised fundamentals, survivorship-biased symbol lists, future constituent membership,
future moderation outcomes, final post scores, or content retrieved after the decision time.
Clock synchronization, market calendars, exchange time zones, halts, splits, dividends, and
delisted symbols require explicit treatment before drawing conclusions.

### Dataset partitions

Time-order every historical experiment and reserve three non-overlapping periods:

1. a discovery/training period for hypotheses and parameter selection;
2. a validation period for limited model and threshold decisions; and
3. a locked final out-of-sample period used once for evaluation.

Do not optimize score weights, thresholds, horizons, community selection, ticker filters, or
decay parameters on the final test period. Record the partition, configuration, code revision,
and run timestamp in `strategy_runs`. A later implementation should add walk-forward analysis
and multiple-testing corrections.

### Mentions, velocity, and manipulation

Ticker extraction recognizes cashtags, unambiguous uppercase symbols, and company names or
aliases from the symbol master. Common words such as `A`, `IT`, `ON`, `ALL`, `FOR`, `ARE`,
`CAN`, `LOVE`, `AI`, `NOW`, and `SO` are rejected as bare tickers; an explicit known cashtag
or company name is required. The master can load normalized exchange CSV data and is not
limited to the included demonstration symbols.

Mention velocity compares five-minute and one-hour activity with a configurable historical
rate and a safe low-volume floor. The preliminary manipulation score flags repeated wording,
repeated URLs, synchronized bursts, author/source concentration, and promotional language.
These heuristics are warnings, not accusations, and must not be used to profile individuals.

### Source, channel, and author scoring

`SOURCE_SCORE` combines directional hit rate and benchmark-adjusted returns, then applies a
minimum-sample penalty, statistical-confidence adjustment, configurable recent-data decay,
and manipulation-risk penalty. Reports retain sample count, raw/median/excess returns,
volatility, consistency, confidence, lead time, recent score, historical score, and combined
score. A tiny winning sample therefore cannot dominate a larger body of evidence.

Author performance is contextual by sector, event type, and horizon. The system does not
assume that an author who appeared useful in one context is globally predictive. Production
research should also examine stability across time, sources, regimes, and ticker liquidity.

### Signal and return scoring

`SIGNAL_SCORE` is a configurable research-prioritization framework combining source quality,
author quality, sentiment strength, discussion velocity, event importance, freshness, news
and market confirmation, liquidity, and manipulation safety. Inputs and weights are stored as
structured values. Arbitrary natural-language output never controls execution. The score does
not claim to predict markets.

Forward-return functions support 5 minutes, 15 minutes, 30 minutes, 1 hour, market close,
1 trading day, and 5 trading days. Both raw and benchmark-adjusted returns are stored.
Benchmarks are selected by country and sector with configurable fallbacks rather than applying
one index to every security.

## Risk controls

Before any future simulated submission, the executor checks connection state, symbol status,
stock/long-only/limit-order restrictions, duplicate client IDs, quote freshness, spread,
minimum price, market cap, liquidity, per-order and per-position value, total exposure, open
positions, daily trade count, and daily loss. Values are based on configurable research capital.
Every decision can be emitted as structured JSON without credentials, balances, or account IDs.

The example paper limits are intentionally modest and are not recommendations.

## Privacy and public-repository safety

No developer identity, account identifier, host identity, private network address, secret,
credential, token, runtime database, or log belongs in this repository. Documentation and
fixtures use generic placeholders and fabricated authors only. Structured logging redacts
sensitive key names. See `SECURITY.md` before committing or publishing.

## Current limitations

- The Reddit adapter is deliberately inactive pending approved API access and policy review.
- Sentiment, event, and manipulation components are transparent deterministic baselines, not
  production-grade classifiers.
- The bundled symbol master is illustrative; broad exchange reference data must be sourced,
  licensed, versioned, and loaded point in time.
- Real historical price/calendar ingestion, corporate-action adjustment, news confirmation,
  FX conversion, and spread/volume confirmation are not yet implemented.
- PostgreSQL support is architecturally separated but not yet integration-tested.
- IBKR paper order status/fill callbacks need durable production persistence and recovery tests
  before `paper-run` can submit.
- Synthetic observations are too small and designed for tests, not inference.

## License

MIT. Third-party data remains subject to its provider's terms and applicable law.
