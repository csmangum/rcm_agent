"""CLI entry point for the RCM agent."""

import click

from rcm_agent import __version__


@click.group()
@click.version_option(version=__version__, prog_name="rcm-agent")
def main() -> None:
    """Hospital RCM Agent – process encounters through eligibility, prior auth, and coding workflows."""
    pass


@main.command()
@click.argument("encounter_file", type=click.Path(exists=True, path_type=str))
def process(encounter_file: str) -> None:
    """Process an encounter from a JSON file."""
    click.echo("Not yet implemented: process")


@main.command()
@click.argument("encounter_id", type=str)
def status(encounter_id: str) -> None:
    """Get current status for an encounter."""
    click.echo("Not yet implemented: status")


@main.command()
@click.argument("encounter_id", type=str)
def history(encounter_id: str) -> None:
    """Get audit trail for an encounter."""
    click.echo("Not yet implemented: history")


@main.command()
def metrics() -> None:
    """Show aggregate metrics (clean rate, escalation %, turnaround)."""
    click.echo("Not yet implemented: metrics")


if __name__ == "__main__":
    main()
