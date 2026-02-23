"""CLI entry point for the RCM agent."""

import json
from pathlib import Path

import click

from rcm_agent import __version__
from rcm_agent.crews.main_crew import process_encounter
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
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        encounter = Encounter.model_validate(data)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON in {encounter_file}: {e}", err=True)
        raise SystemExit(1)
    except Exception as e:
        click.echo(f"Invalid encounter data in {encounter_file}: {e}", err=True)
        raise SystemExit(1)
    repo = _repo(ctx)

    # Save as PENDING (INTAKE = unrouted), then PROCESSING
    repo.save_encounter(encounter, RcmStage.INTAKE, EncounterStatus.PENDING)
    repo.update_status(
        encounter.encounter_id,
        EncounterStatus.PROCESSING,
        "process_started",
        details="Router and pipeline started",
    )

    output = process_encounter(encounter)
    repo.update_status(
        encounter.encounter_id,
        output.status,
        "workflow_complete",
        new_stage=output.stage,
        details=output.message,
    )
    router_output = {
        "stage": output.stage.value,
        "confidence": output.raw_result.get("router_confidence"),
        "reasoning": output.raw_result.get("router_reasoning") or "",
        "escalation_reasons": output.raw_result.get("escalation_reasons"),
    }
    repo.save_workflow_run(
        encounter.encounter_id,
        output.stage,
        router_output,
        output.model_dump(),
    )

    if output.stage == RcmStage.DENIAL_APPEAL and output.raw_result:
        repo.save_denial_event(
            encounter_id=encounter.encounter_id,
            reason_codes=output.raw_result.get("reason_codes") or [],
            denial_type=output.raw_result.get("denial_type") or "clinical",
            appeal_viable=output.raw_result.get("appeal_viable", True),
            claim_id=output.raw_result.get("claim_id"),
            payer=encounter.insurance.payer,
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
    denial_stats = m.get("denial_stats", {})
    if denial_stats and denial_stats.get("total", 0) > 0:
        click.echo("Denial events:")
        click.echo(f"  Total: {denial_stats['total']} (appeal viable: {denial_stats.get('appeal_viable_count', 0)})")
        for code, count in sorted(denial_stats.get("by_reason_code", {}).items()):
            click.echo(f"  Reason {code}: {count}")
        for dtype, count in sorted(denial_stats.get("by_denial_type", {}).items()):
            click.echo(f"  Type {dtype}: {count}")


@main.command()
@click.pass_context
def denial_stats(ctx: click.Context) -> None:
    """Show denial analytics (reason codes, denial type, payer)."""
    repo = _repo(ctx)
    stats = repo.get_denial_stats()
    click.echo(f"Total denial events: {stats['total']}")
    click.echo(f"Appeal viable: {stats['appeal_viable_count']}")
    click.echo("By reason code:")
    for code, count in sorted(stats["by_reason_code"].items()):
        click.echo(f"  {code}: {count}")
    click.echo("By denial type:")
    for dtype, count in sorted(stats["by_denial_type"].items()):
        click.echo(f"  {dtype}: {count}")
    click.echo("By payer:")
    for payer, count in sorted(stats["by_payer"].items()):
        click.echo(f"  {payer}: {count}")


if __name__ == "__main__":
    main()
