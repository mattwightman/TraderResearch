"""Command-line interface for synthetic research and paper status."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from traderresearch.analysis.pipeline import AnalysisPipeline
from traderresearch.config import AppConfig, load_config
from traderresearch.logging_config import configure_logging
from traderresearch.market.symbols import sample_symbol_master
from traderresearch.reddit.mock_collector import MockRedditCollector
from traderresearch.storage.database import Database
from traderresearch.storage.repository import ResearchRepository
from traderresearch.trading.ibkr import IbkrPaperClient, MockIbkrClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traderresearch",
        description=(
            "Research public social-market signals with synthetic data and "
            "strictly paper-only trading safeguards."
        ),
    )
    parser.add_argument("--config", type=Path, help="Optional YAML configuration file.")
    parser.add_argument(
        "--database",
        type=Path,
        help="Optional SQLite path; defaults to external application data storage.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser(
        "ingest-sample", help="Ingest bundled, entirely synthetic Reddit-style content."
    )
    ingest.add_argument(
        "--sample-file",
        type=Path,
        help="Optional local synthetic JSON file instead of the bundled fixture.",
    )
    subparsers.add_parser(
        "analyze", help="Extract mentions and build point-in-time research scores."
    )
    leaderboard = subparsers.add_parser(
        "leaderboard", help="Show confidence-adjusted channel performance."
    )
    leaderboard.add_argument("--limit", type=int, default=20)
    authors = subparsers.add_parser(
        "authors", help="Show author performance by sector and event context."
    )
    authors.add_argument("--limit", type=int, default=20)
    signals = subparsers.add_parser(
        "signals", help="Show generated research signals; these are not trade advice."
    )
    signals.add_argument("--limit", type=int, default=20)
    subparsers.add_parser("evaluate", help="Summarize persisted synthetic evaluation records.")
    paper_status = subparsers.add_parser(
        "paper-status",
        help="Check an IBKR paper session without displaying account identifiers.",
    )
    paper_status.add_argument(
        "--mock", action="store_true", help="Use the no-network paper test double."
    )
    paper_run = subparsers.add_parser(
        "paper-run",
        help="Run the guarded paper workflow; order submission is config-disabled by default.",
    )
    paper_run.add_argument(
        "--mock", action="store_true", help="Use the no-network paper test double."
    )
    return parser


def _repository(config: AppConfig, database_path: Path | None) -> ResearchRepository:
    database = Database.from_sqlite_path(database_path or config.database_path)
    database.initialize_schema()
    repository = ResearchRepository(database)
    repository.upsert_symbols(sample_symbol_master().active_symbols())
    return repository


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "No records. Run ingest-sample and analyze first."
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row, strict=True)]
    header_line = "  ".join(
        header.ljust(width) for header, width in zip(headers, widths, strict=True)
    )
    divider = "  ".join("-" * width for width in widths)
    body = [
        "  ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))
        for row in rows
    ]
    return "\n".join([header_line, divider, *body])


def _ingest(repository: ResearchRepository, sample_file: Path | None) -> int:
    inserted = repository.ingest_content(MockRedditCollector(sample_file).collect())
    total = repository.record_counts()["content"]
    print(f"Ingested {inserted} synthetic records; {total} total records are available.")
    return 0


def _analyze(repository: ResearchRepository, config: AppConfig) -> int:
    summary = AnalysisPipeline(repository, sample_symbol_master(), config.analysis).run()
    print(
        "Analysis complete: "
        f"{summary.content_count} content records, {summary.mention_count} mentions, "
        f"{summary.signal_count} signals, {summary.source_scores} source scores, "
        f"and {summary.author_scores} contextual author scores."
    )
    return 0


def _leaderboard(repository: ResearchRepository, limit: int) -> int:
    performances = [
        score
        for score in repository.list_source_performance()
        if score.sector is None and score.event_type is None and score.horizon == "1d"
    ][:limit]
    rows = [
        [
            score.key,
            str(score.sample_count),
            f"{score.directional_hit_rate:.1%}",
            f"{score.average_benchmark_adjusted_return:.2%}",
            f"{score.statistical_confidence:.2f}",
            f"{score.manipulation_risk:.2f}",
            f"{score.combined_score:.1f}",
        ]
        for score in performances
    ]
    print(
        _format_table(
            ["SOURCE", "N", "HIT RATE", "AVG EXCESS", "CONF", "MANIP", "SOURCE_SCORE"],
            rows,
        )
    )
    return 0


def _authors(repository: ResearchRepository, limit: int) -> int:
    rows = [
        [
            score.key,
            score.sector or "*",
            score.event_type or "*",
            score.horizon,
            str(score.sample_count),
            f"{score.directional_hit_rate:.1%}",
            f"{score.combined_score:.1f}",
        ]
        for score in repository.list_author_performance()[:limit]
    ]
    print(
        _format_table(
            ["AUTHOR", "SECTOR", "EVENT", "HORIZON", "N", "HIT RATE", "SCORE"],
            rows,
        )
    )
    return 0


def _signals(repository: ResearchRepository, limit: int) -> int:
    rows = [
        [
            signal.signal_id,
            signal.ticker,
            signal.direction.value,
            signal.subreddit,
            signal.event_type,
            f"{signal.signal_score:.1f}",
            f"{signal.manipulation_score:.2f}",
            signal.signal_generated_time.isoformat(),
        ]
        for signal in repository.list_signals(limit)
    ]
    print(
        _format_table(
            ["SIGNAL", "TICKER", "DIRECTION", "SOURCE", "EVENT", "SCORE", "MANIP", "GENERATED"],
            rows,
        )
    )
    return 0


def _evaluate(repository: ResearchRepository) -> int:
    counts = repository.record_counts()
    print(
        "Synthetic evaluation records: "
        f"{counts['signals']} signals and {counts['forward_returns']} forward returns. "
        "Use separate discovery, validation, and final out-of-sample periods for real research."
    )
    return 0


def _paper_status(config: AppConfig, use_mock: bool) -> int:
    client = MockIbkrClient(config.ibkr) if use_mock else IbkrPaperClient(config.ibkr)
    try:
        client.connect()
        status = client.read_account_summary()
        print(
            f"Environment: {status.environment}; connected: {str(status.connected).lower()}; "
            f"positions: {status.positions_count}; open orders: {status.open_orders_count}."
        )
        print(status.message)
    except (ConnectionError, RuntimeError) as error:
        print(f"Paper status unavailable: {error}", file=sys.stderr)
        return 2
    finally:
        client.disconnect()
    return 0


def _paper_run(config: AppConfig, use_mock: bool) -> int:
    if not config.ibkr.order_submission_enabled:
        print(
            "Paper workflow stopped safely: order submission is disabled in configuration. "
            "No order was submitted."
        )
        return 0
    client = MockIbkrClient(config.ibkr) if use_mock else IbkrPaperClient(config.ibkr)
    try:
        client.connect()
        print(
            "Paper session connected. No order was submitted because this release requires "
            "a point-in-time market-data adapter before execution."
        )
    finally:
        client.disconnect()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        configure_logging(config.log_level)
        if args.command == "paper-status":
            return _paper_status(config, args.mock)
        if args.command == "paper-run":
            return _paper_run(config, args.mock)
        repository = _repository(config, args.database)
        if args.command == "ingest-sample":
            return _ingest(repository, args.sample_file)
        if args.command == "analyze":
            return _analyze(repository, config)
        if args.command == "leaderboard":
            return _leaderboard(repository, args.limit)
        if args.command == "authors":
            return _authors(repository, args.limit)
        if args.command == "signals":
            return _signals(repository, args.limit)
        if args.command == "evaluate":
            return _evaluate(repository)
    except (OSError, ValueError, RuntimeError, LookupError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
