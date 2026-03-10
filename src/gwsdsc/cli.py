"""Command-line interface for GoogleWorkspaceDsc.

Usage::

    gwsdsc export --config config/tenant.yaml
    gwsdsc diff   --baseline artifacts/v1 --target artifacts/v2
    gwsdsc apply  --config config/tenant.yaml --source artifacts/latest --plan
    gwsdsc report --diff-json diff-result.json --format html --output report.html
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

app = typer.Typer(
    name="gwsdsc",
    help="GoogleWorkspaceDsc — Configuration as Code for Google Workspace",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@app.command()
def export(
    config: str = typer.Option("config/tenant.yaml", "--config", "-c", help="Tenant config file"),
    resources: Optional[str] = typer.Option(None, "--resources", "-r", help="Comma-separated resource list"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory override"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Export tenant configuration to versioned artifacts."""
    _setup_logging(verbose)

    from gwsdsc.config import load_tenant_config
    from gwsdsc.engine.export_engine import ExportEngine

    cfg = load_tenant_config(config)
    engine = ExportEngine(cfg)

    resource_list = resources.split(",") if resources else None
    snapshot = engine.run(resource_names=resource_list, output_dir=output)

    # Pretty-print summary
    meta = snapshot["metadata"]
    console.print(f"\n[bold green]Export complete[/]")
    console.print(f"  Tenant:    {meta['tenant_name']}")
    console.print(f"  Domain:    {meta['primary_domain']}")
    console.print(f"  Timestamp: {meta['exported_at']}")

    table = Table(title="Exported Resources")
    table.add_column("Resource", style="cyan")
    table.add_column("Items", justify="right")
    table.add_column("Status")

    for name in meta["resources_exported"]:
        data = snapshot["resources"].get(name)
        if isinstance(data, list):
            table.add_row(name, str(len(data)), "[green]OK[/]")
        elif isinstance(data, dict) and "_error" in data:
            table.add_row(name, "—", f"[red]Error: {data['_error'][:60]}[/]")
        else:
            table.add_row(name, "—", "[yellow]Unknown[/]")

    console.print(table)

    if meta.get("errors"):
        console.print(f"\n[yellow]⚠ {len(meta['errors'])} resource(s) had errors[/]")


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

@app.command()
def diff(
    baseline: str = typer.Option(..., "--baseline", "-b", help="Baseline snapshot directory"),
    target: str = typer.Option(..., "--target", "-t", help="Target snapshot directory"),
    resources: Optional[str] = typer.Option(None, "--resources", "-r", help="Comma-separated resource filter"),
    report: Optional[str] = typer.Option(None, "--report", help="Report format: html, markdown, json"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Report output file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Compare two snapshots and report drift."""
    _setup_logging(verbose)

    from gwsdsc.engine.diff_engine import DiffEngine
    from gwsdsc.engine.report_engine import ReportEngine

    resource_list = resources.split(",") if resources else None
    result = DiffEngine.compare(baseline, target, resource_names=resource_list)

    # Print summary table
    table = Table(title="Configuration Drift Summary")
    table.add_column("Resource", style="cyan")
    table.add_column("Added", justify="right", style="green")
    table.add_column("Removed", justify="right", style="red")
    table.add_column("Modified", justify="right", style="yellow")

    for name, rd in result.resources.items():
        if rd.has_changes:
            table.add_row(name, str(len(rd.added)), str(len(rd.removed)), str(len(rd.modified)))

    console.print(table)
    console.print(f"\n[bold]Total changes: {result.total_changes}[/]")

    # Generate report if requested
    if report:
        out_path = output or f"drift-report.{report if report != 'markdown' else 'md'}"
        content = ReportEngine.generate(result, format=report, output=out_path)
        console.print(f"[green]Report written to {out_path}[/]")

    # Always write JSON diff
    diff_json = Path(output).with_suffix(".json") if output else Path("diff-result.json")
    diff_json.write_text(result.to_json())
    console.print(f"Diff JSON written to {diff_json}")


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

@app.command()
def apply(
    config: str = typer.Option("config/tenant.yaml", "--config", "-c", help="Target tenant config"),
    source: str = typer.Option(..., "--source", "-s", help="Source snapshot directory"),
    plan: bool = typer.Option(False, "--plan", "-p", help="Dry-run — show what would change"),
    confirm: bool = typer.Option(False, "--confirm", help="Actually apply changes"),
    allow_delete: bool = typer.Option(False, "--allow-delete", help="Allow deletion of extra resources"),
    resources: Optional[str] = typer.Option(None, "--resources", "-r", help="Comma-separated resource filter"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Apply a snapshot to a target tenant (dry-run by default)."""
    _setup_logging(verbose)

    from gwsdsc.config import load_tenant_config
    from gwsdsc.engine.import_engine import ImportEngine, ImportMode

    if not plan and not confirm:
        console.print("[yellow]Neither --plan nor --confirm specified. Defaulting to --plan.[/]")
        plan = True

    cfg = load_tenant_config(config)
    engine = ImportEngine(cfg, allow_delete=allow_delete)
    mode = ImportMode.PLAN if plan else ImportMode.APPLY

    resource_list = resources.split(",") if resources else None
    result = engine.run(source_dir=source, mode=mode, resource_names=resource_list)

    # Print actions
    table = Table(title=f"Import {'Plan' if plan else 'Results'}")
    table.add_column("Resource", style="cyan")
    table.add_column("Key")
    table.add_column("Action", style="bold")
    table.add_column("Details")

    for action in result.actions:
        style = {
            "create": "green",
            "update": "yellow",
            "delete": "red",
            "skip": "dim",
            "error": "bold red",
        }.get(action.action, "")
        table.add_row(
            action.resource_name,
            action.key[:50],
            f"[{style}]{action.action}[/{style}]",
            action.details[:80] if action.details else "",
        )

    console.print(table)
    console.print(f"\nSummary: {result.summary}")

    if plan:
        console.print("\n[yellow]This was a dry-run. Use --confirm to apply changes.[/]")


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

@app.command()
def store(
    action: str = typer.Argument(help="Action: commit, list, checkout"),
    config: str = typer.Option("config/tenant.yaml", "--config", "-c"),
    snapshot_dir: Optional[str] = typer.Option(None, "--snapshot-dir"),
    version: Optional[str] = typer.Option(None, "--version"),
    target_dir: Optional[str] = typer.Option(None, "--target-dir"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Manage the versioned artifact store (commit / list / checkout)."""
    _setup_logging(verbose)

    from gwsdsc.config import load_tenant_config

    cfg = load_tenant_config(config)

    if cfg.store.type == "git":
        from gwsdsc.store.git_store import GitStore

        st = GitStore(cfg.store)
    elif cfg.store.type == "gcs":
        from gwsdsc.store.gcs_store import GCSStore

        st = GCSStore(cfg.store)
    else:
        console.print(f"[red]Store type '{cfg.store.type}' not supported for this command[/]")
        raise typer.Exit(1)

    if action == "commit":
        if not snapshot_dir:
            console.print("[red]--snapshot-dir is required for commit[/]")
            raise typer.Exit(1)
        sha = st.commit(Path(snapshot_dir))
        console.print(f"[green]Committed: {sha}[/]")

    elif action == "list":
        versions = st.list_versions()
        table = Table(title="Snapshot Versions")
        table.add_column("Version / Tag")
        table.add_column("Date")
        table.add_column("Message")
        for v in versions:
            table.add_row(
                v.get("tag", v.get("version", "")),
                v.get("date", ""),
                v.get("message", ""),
            )
        console.print(table)

    elif action == "checkout":
        if not version or not target_dir:
            console.print("[red]--version and --target-dir required for checkout[/]")
            raise typer.Exit(1)
        path = st.checkout(version, Path(target_dir))
        console.print(f"[green]Checked out to: {path}[/]")

    else:
        console.print(f"[red]Unknown action: {action}[/]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# catalogue
# ---------------------------------------------------------------------------

@app.command()
def catalogue(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List all available resource modules."""
    _setup_logging(verbose)

    from gwsdsc.config import load_resource_catalogue

    cat = load_resource_catalogue()

    table = Table(title="Resource Module Catalogue")
    table.add_column("Name", style="cyan")
    table.add_column("API Service")
    table.add_column("Importable", justify="center")
    table.add_column("Description")

    for entry in cat.resources:
        table.add_row(
            entry.name,
            f"{entry.api_service}/{entry.api_version}",
            "[green]✓[/]" if entry.importable else "[dim]—[/]",
            entry.description,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
