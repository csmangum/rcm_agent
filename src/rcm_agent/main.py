"""CLI entry point for the RCM agent."""

import json
from pathlib import Path

import click

from rcm_agent import __version__
from rcm_agent.crews.stub import run_stub_crew
from rcm_agent.db import EncounterRepository
from rcm_agent.models import Encounter, EncounterStatus, RcmStage


@click.group()
@click.version_option(version=__version__, prog_name="rcm-agent")
@click.option(
    "--db-path",
    envvar="RCM_DB_PATH",
    default="data/rcm.db",
    type=click.Path(path_type=str),
    help="Path to SQLite database (default: data/rcm.db or RCM_DB_PATH).",
)
@click.pass_context
def main(ctx: click.Context, db_path: str) -> None:
    """Hospital RCM Agent – process encounters through eligibility, prior auth, and coding workflows."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path


def _repo(ctx: click.Context) -> EncounterRepository:
    return EncounterRepository(ctx.obj["db_path"])


@main.command()
@click.argument("encounter_file", type=click.Path(exists=True, path_type=str))
@click.pass_context
def process(ctx: click.Context, encounter_file: str) -> None:
    """Process an encounter from a JSON file."""
    path = Path(encounter_file)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    encounter = Encounter.model_validate(data)
    repo = _repo(ctx)

    # Save as PENDING, then PROCESSING
    repo.save_encounter(encounter, RcmStage.ELIGIBILITY_VERIFICATION, EncounterStatus.PENDING)
    repo.update_status(
        encounter.encounter_id,
        EncounterStatus.PROCESSING,
        "process_started",
        details="Stub pipeline started",
    )

    # Stub crew returns mock output
    output = run_stub_crew(encounter)
    repo.update_status(
        encounter.encounter_id,
        output.status,
        "stub_workflow_complete",
        new_stage=output.stage,
        details=output.message,
    )
    repo.save_workflow_run(
        encounter.encounter_id,
        output.stage,
        {"stub": True},
        output.model_dump(),
    )

    click.echo(f"Encounter {encounter.encounter_id}: stage={output.stage.value}, status={output.status.value}")
    click.echo(output.message)


@main.command()
@click.argument("encounter_id", type=str)
@click.pass_context
def status(ctx: click.Context, encounter_id: str) -> None:
    """Get current status for an encounter."""
    repo = _repo(ctx)
    row = repo.get_encounter(encounter_id)
    if not row:
        click.echo(f"Encounter {encounter_id} not found.", err=True)
        raise SystemExit(1)
    click.echo(f"Encounter: {row['encounter_id']}")
    click.echo(f"Stage:     {row['stage']}")
    click.echo(f"Status:    {row['status']}")
    click.echo(f"Updated:   {row['updated_at']}")


@main.command()
@click.argument("encounter_id", type=str)
@click.pass_context
def history(ctx: click.Context, encounter_id: str) -> None:
    """Get audit trail for an encounter."""
    repo = _repo(ctx)
    if repo.get_encounter(encounter_id) is None:
        click.echo(f"Encounter {encounter_id} not found.", err=True)
        raise SystemExit(1)
    entries = repo.get_audit_log(encounter_id)
    if not entries:
        click.echo("No audit log entries.")
        return
    for e in entries:
        click.echo(f"{e['created_at']} | {e['action']} | {e['old_status']} -> {e['new_status']}")


@main.command()
@click.pass_context
def metrics(ctx: click.Context) -> None:
    """Show aggregate metrics (clean rate, escalation %, turnaround)."""
    repo = _repo(ctx)
    m = repo.get_metrics()
    total = m["total"]
    click.echo(f"Total encounters: {total}")
    click.echo(f"Clean rate:       {m['clean_rate_pct']:.1f}% ({m['clean_count']})")
    click.echo(f"Escalation %:     {m['escalation_pct']:.1f}% ({m['escalated_count']})")
    click.echo("By status:")
    for status, count in sorted(m["by_status"].items()):
        click.echo(f"  {status}: {count}")
    click.echo("By stage:")
    for stage, count in sorted(m["by_stage"].items()):
        click.echo(f"  {stage}: {count}")


if __name__ == "__main__":
    main()
