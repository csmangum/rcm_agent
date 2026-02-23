"""Unit tests for CLI commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from rcm_agent.main import main


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "rcm.db")


def test_process_command(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """process loads JSON, validates, saves to DB, runs router pipeline."""
    encounter_file = examples_dir / "encounter_001_routine_visit.json"
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    assert result.exit_code == 0
    assert "ENC-001" in result.output
    assert "stage=" in result.output
    assert "status=" in result.output


def test_status_command(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """status prints encounter stage/status after process."""
    encounter_file = examples_dir / "encounter_001_routine_visit.json"
    cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "status", "ENC-001"])
    assert result.exit_code == 0
    assert "ENC-001" in result.output
    assert "Stage:" in result.output
    assert "Status:" in result.output


def test_status_command_not_found(cli_runner: CliRunner, tmp_db_path: str) -> None:
    """status for unknown encounter exits non-zero."""
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "status", "ENC-NONE"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_history_command(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """history prints audit log after process."""
    encounter_file = examples_dir / "encounter_001_routine_visit.json"
    cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "history", "ENC-001"])
    assert result.exit_code == 0
    assert "process_started" in result.output or "workflow_complete" in result.output


def test_history_command_not_found(cli_runner: CliRunner, tmp_db_path: str) -> None:
    """history for unknown encounter exits non-zero."""
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "history", "ENC-NONE"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_metrics_command(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """metrics shows aggregate counts."""
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "metrics"])
    assert result.exit_code == 0
    assert "Total encounters:" in result.output
    assert "Clean rate:" in result.output
    assert "Escalation" in result.output

    encounter_file = examples_dir / "encounter_001_routine_visit.json"
    cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    result2 = cli_runner.invoke(main, ["--db-path", tmp_db_path, "metrics"])
    assert result2.exit_code == 0
    assert "Total encounters: 1" in result2.output or "1" in result2.output


def test_help(cli_runner: CliRunner) -> None:
    """--help prints usage."""
    result = cli_runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "process" in result.output
    assert "status" in result.output
    assert "history" in result.output
    assert "metrics" in result.output
    assert "denial-stats" in result.output


def test_process_encounter_004_denial_crew(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """process encounter_004 runs denial/appeal crew and succeeds."""
    encounter_file = examples_dir / "encounter_004_denial_scenario.json"
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    assert result.exit_code == 0
    assert "ENC-004" in result.output
    assert "DENIAL_APPEAL" in result.output


def test_denial_stats_command(cli_runner: CliRunner, examples_dir: Path, tmp_db_path: str) -> None:
    """denial-stats shows analytics after processing a denial encounter."""
    result = cli_runner.invoke(main, ["--db-path", tmp_db_path, "denial-stats"])
    assert result.exit_code == 0
    assert "Total denial events:" in result.output
    encounter_file = examples_dir / "encounter_004_denial_scenario.json"
    cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    result2 = cli_runner.invoke(main, ["--db-path", tmp_db_path, "denial-stats"])
    assert result2.exit_code == 0
    assert "1" in result2.output  # at least one event
    assert "By reason code:" in result2.output or "By denial type:" in result2.output
