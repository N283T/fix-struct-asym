#!/usr/bin/env python3
"""CLI for finding missing struct_asym entries in PDB CIF files."""

from __future__ import annotations

import json
import multiprocessing
import random
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from fix_struct_asym.cli._common import (
    DEFAULT_WORKERS,
    console,
    create_progress,
    err_console,
)
from fix_struct_asym.core import enumerate_cif_files
from fix_struct_asym.find import _process_file, result_to_dict
from fix_struct_asym.models import MissingAsymResult, ScanResult

app = typer.Typer(
    name="find-missing-struct-asym",
    help="Detect PDB entries with missing _struct_asym entries.",
    add_completion=False,
    rich_markup_mode="rich",
)


def _scan_with_progress(
    files: list[str],
    workers: int,
    quiet: bool,
) -> list[MissingAsymResult]:
    """Scan files with optional progress display.

    Args:
        files: List of file paths to scan.
        workers: Number of parallel workers.
        quiet: If True, suppress progress output.

    Returns:
        List of MissingAsymResult for files with missing entries.
    """
    results: list[MissingAsymResult] = []

    with multiprocessing.Pool(processes=workers) as pool:
        if quiet:
            for result in pool.imap_unordered(_process_file, files):
                if result is not None:
                    results.append(result)
        else:
            with create_progress() as progress:
                task = progress.add_task("[cyan]Scanning files...", total=len(files))
                for result in pool.imap_unordered(_process_file, files):
                    if result is not None:
                        results.append(result)
                    progress.update(task, advance=1)

    return results


def display_summary(result: ScanResult) -> None:
    """Display a rich summary of scan results."""
    summary_text = (
        f"[bold]Scan Date:[/] {result.scan_date}\n"
        f"[bold]Total Scanned:[/] {result.total_scanned:,}\n"
        f"[bold]Affected Entries:[/] {result.affected_entries:,}"
    )

    if result.affected_entries > 0:
        percentage = (result.affected_entries / result.total_scanned) * 100
        summary_text += f" ([yellow]{percentage:.2f}%[/])"

    err_console.print(
        Panel(summary_text, title="[bold blue]Scan Summary", border_style="blue")
    )

    if result.entries:
        table = Table(title="Missing struct_asym Entries Found", show_lines=True)
        table.add_column("PDB ID", style="cyan", no_wrap=True)
        table.add_column("Missing Asym IDs", style="yellow")
        table.add_column("Components", style="green")
        table.add_column("Total Atoms", justify="right", style="magenta")

        display_entries = result.entries[:20]
        for entry in display_entries:
            asym_str = ", ".join(entry.missing_asym_ids)
            comps = set()
            total_atoms = 0
            for detail in entry.details.values():
                comps.update(detail.comp_ids)
                total_atoms += detail.atom_count
            comps_str = ", ".join(sorted(comps))
            table.add_row(entry.pdb_id.upper(), asym_str, comps_str, str(total_atoms))

        if len(result.entries) > 20:
            table.add_row(
                f"... and {len(result.entries) - 20} more",
                "",
                "",
                "",
                style="dim",
            )

        err_console.print(table)


@app.command()
def main(
    mirror_path: Annotated[
        Path | None,
        typer.Option(
            "--mirror-path",
            "-m",
            help="Path to PDB mirror root directory",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    files: Annotated[
        list[Path] | None,
        typer.Option(
            "--files",
            "-f",
            help="Specific CIF files to scan",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output JSON file (default: stdout)",
        ),
    ] = None,
    workers: Annotated[
        int,
        typer.Option(
            "--workers",
            "-w",
            help="Number of parallel workers",
            min=1,
            max=32,
        ),
    ] = DEFAULT_WORKERS,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output raw JSON only (no rich formatting)",
        ),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            "-l",
            help="Limit scan to N randomly sampled files",
            min=1,
        ),
    ] = None,
) -> None:
    """Detect missing struct_asym entries in PDB CIF files.

    Scans CIF files to find asym IDs that exist in _atom_site but are missing
    from _struct_asym. This indicates a data inconsistency in the PDB entry.

    [bold]Examples:[/]

        # Scan specific files
        [cyan]find-missing-struct-asym -f 2g10.cif.gz -f 1ts6.cif.gz[/]

        # Scan entire PDB mirror
        [cyan]find-missing-struct-asym -m /path/to/pdb/mirror -o results.json[/]

        # Scan 100 random files from PDB mirror
        [cyan]find-missing-struct-asym -m /path/to/pdb/mirror --limit 100[/]

        # Output raw JSON only
        [cyan]find-missing-struct-asym -f 2g10.cif.gz --json[/]
    """
    # Validate arguments
    if mirror_path is None and files is None:
        err_console.print(
            "[red]Error:[/] Either --mirror-path or --files must be specified"
        )
        raise typer.Exit(code=1)

    if mirror_path is not None and files is not None:
        err_console.print(
            "[red]Error:[/] Cannot specify both --mirror-path and --files"
        )
        raise typer.Exit(code=1)

    # Show configuration
    if not json_output:
        config_text = (
            f"[bold]Workers:[/] {workers}\n[bold]Output:[/] {output or 'stdout'}"
        )
        if limit:
            config_text += f"\n[bold]Limit:[/] {limit:,} files (random sample)"
        err_console.print(
            Panel(
                config_text,
                title="[bold green]Configuration",
                border_style="green",
            )
        )

    # Collect file paths
    if files:
        file_paths = [str(f) for f in files]
    else:
        assert mirror_path is not None
        if not json_output:
            with err_console.status("[bold blue]Enumerating CIF files..."):
                file_paths = enumerate_cif_files(mirror_path)
            err_console.print(f"[green]Found {len(file_paths):,} CIF files[/]")
        else:
            file_paths = enumerate_cif_files(mirror_path)

    # Apply limit if specified (random sample)
    if limit is not None and limit < len(file_paths):
        if not json_output:
            err_console.print(
                f"[yellow]Limiting to {limit:,} randomly sampled files[/]"
            )
        file_paths = random.sample(file_paths, limit)

    # Run scan
    from datetime import date

    results = _scan_with_progress(file_paths, workers, json_output)
    results.sort(key=lambda r: r.pdb_id)

    scan_result = ScanResult(
        scan_date=date.today().isoformat(),
        total_scanned=len(file_paths),
        affected_entries=len(results),
        entries=results,
    )

    # Output results
    output_dict = result_to_dict(scan_result)
    json_str = json.dumps(output_dict, indent=2)

    if output:
        output.write_text(json_str)
        if not json_output:
            err_console.print(f"[green]Results written to {output}[/]")
    else:
        console.print(json_str)

    # Display summary
    if not json_output:
        display_summary(scan_result)


if __name__ == "__main__":
    app()
