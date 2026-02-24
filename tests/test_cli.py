"""Unit tests for CLI commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rcm_agent.main import main
from rcm_agent.models import EncounterOutput, EncounterStatus, RcmStage


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
    assert "eval-router" in result.output
    assert "eval-e2e" in result.output
    assert "eval-all" in result.output


def test_eval_router_command(cli_runner: CliRunner, examples_dir: Path, tmp_path: Path) -> None:
    """eval-router runs heuristic comparison, writes report."""
    output = tmp_path / "router_report.json"
    result = cli_runner.invoke(
        main,
        ["eval-router", "--examples-dir", str(examples_dir), "-o", str(output)],
    )
    assert result.exit_code == 0
    assert "Encounters evaluated:" in result.output
    assert "Agreement rate:" in result.output
    assert output.exists()
    data = json.loads(output.read_text())
    assert "total" in data
    assert "records" in data


def test_eval_e2e_command_mocked(cli_runner: CliRunner, examples_dir: Path, tmp_path: Path) -> None:
    """eval-e2e runs (with mocked pipeline in unit tests, real in e2e)."""
    from unittest.mock import patch

    with patch("rcm_agent.crews.e2e_eval.process_encounter_multi_stage") as mock:
        mock.return_value = [
            EncounterOutput(
                encounter_id="ENC-001",
                stage=RcmStage.CODING_CHARGE_CAPTURE,
                status=EncounterStatus.CODED,
                actions_taken=[],
                artifacts=[],
                message="Coded",
                raw_result={},
            ),
            EncounterOutput(
                encounter_id="ENC-001",
                stage=RcmStage.CLAIMS_SUBMISSION,
                status=EncounterStatus.CLAIM_SUBMITTED,
                actions_taken=[],
                artifacts=[],
                message="Submitted",
                raw_result={},
            ),
        ]
        result = cli_runner.invoke(
            main,
            [
                "eval-e2e",
                "--examples-dir",
                str(examples_dir),
                "-o",
                str(tmp_path / "e2e_report.json"),
            ],
        )
    assert result.exit_code == 0
    assert "Pipeline success rate:" in result.output
    assert (tmp_path / "e2e_report.json").exists()
    assert (tmp_path / "e2e_report.md").exists()


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
    assert "Total denial events: 0" in result.output
    encounter_file = examples_dir / "encounter_004_denial_scenario.json"
    cli_runner.invoke(main, ["--db-path", tmp_db_path, "process", str(encounter_file)])
    result2 = cli_runner.invoke(main, ["--db-path", tmp_db_path, "denial-stats"])
    assert result2.exit_code == 0
    assert "1" in result2.output  # at least one event
    assert "By reason code:" in result2.output or "By denial type:" in result2.output
