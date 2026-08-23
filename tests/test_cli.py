from __future__ import annotations

from pathlib import Path

from traderresearch.cli import main


def test_required_cli_workflow(tmp_path: Path, capsys: object) -> None:
    database = tmp_path / "cli.sqlite3"
    base = ["--database", str(database)]
    assert main([*base, "ingest-sample"]) == 0
    assert main([*base, "analyze"]) == 0
    assert main([*base, "leaderboard"]) == 0
    assert main([*base, "signals", "--limit", "3"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Ingested" in output
    assert "Analysis complete" in output
    assert "SOURCE_SCORE" in output
    assert "TICKER" in output


def test_cli_ingestion_is_idempotent(tmp_path: Path, capsys: object) -> None:
    database = tmp_path / "cli.sqlite3"
    args = ["--database", str(database), "ingest-sample"]
    assert main(args) == 0
    assert main(args) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Ingested 0 synthetic records" in output


def test_paper_status_mock_is_non_sensitive(capsys: object) -> None:
    assert main(["paper-status", "--mock"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "Environment: paper" in output
    assert "account number" not in output.casefold()
    assert "balance" not in output.casefold()


def test_paper_run_submits_nothing_by_default(capsys: object) -> None:
    assert main(["paper-run", "--mock"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "No order was submitted" in output
