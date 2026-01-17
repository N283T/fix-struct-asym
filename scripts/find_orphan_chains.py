#!/usr/bin/env python3
"""Detect PDB entries where chains exist in _atom_site but not in _struct_asym.

This script scans CIF files to find "orphan chains" - chains that are present
in the _atom_site category but missing from the _struct_asym category.
"""

from __future__ import annotations

import json
import multiprocessing
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated

import gemmi
import typer
from gemmi import cif
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

# Default number of workers: use half of CPU cores, minimum 1, maximum 8
DEFAULT_WORKERS = min(8, max(1, (os.cpu_count() or 4) // 2))

# Rich console for output
console = Console()
err_console = Console(stderr=True)

# Typer app
app = typer.Typer(
    name="find-orphan-chains",
    help="Detect PDB entries where chains exist in _atom_site but not in _struct_asym.",
    add_completion=False,
    rich_markup_mode="rich",
)


@dataclass
class ChainDetails:
    """Details about an orphan chain."""

    comp_ids: list[str]
    atom_count: int


@dataclass
class OrphanResult:
    """Result of orphan chain detection for a single file."""

    pdb_id: str
    file_path: str
    orphan_chains: list[str]
    details: dict[str, ChainDetails] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Result of scanning multiple files."""

    scan_date: str
    total_scanned: int
    affected_entries: int
    entries: list[OrphanResult]


def find_orphan_chains(cif_path: str) -> OrphanResult | None:
    """Detect orphan chains in a single CIF file.

    Args:
        cif_path: Path to the CIF file to analyze (handles .gz automatically).

    Returns:
        OrphanResult if orphan chains are found, None otherwise.
    """
    try:
        doc = cif.read(cif_path)
    except (RuntimeError, OSError) as e:
        # RuntimeError: gemmi CIF parsing errors
        # OSError: file access issues
        err_console.print(f"[yellow]Warning:[/] Error reading {cif_path}: {e}")
        return None

    # Explicit length check for empty document
    if len(doc) == 0:
        return None

    block = doc[0]
    pdb_id = block.name.lower()

    # Extract chain IDs from _struct_asym using cif.as_string for proper handling
    struct_asym_ids: set[str] = set()
    struct_asym = block.find("_struct_asym.", ["id"])
    if struct_asym:
        for row in struct_asym:
            struct_asym_ids.add(cif.as_string(row[0]))

    # Extract chain info from _atom_site: track comp_ids and atom_count per chain
    chain_comp_ids: dict[str, set[str]] = {}
    chain_atom_counts: dict[str, int] = {}

    atom_site = block.find("_atom_site.", ["label_asym_id", "label_comp_id"])
    if atom_site:
        for row in atom_site:
            asym_id = cif.as_string(row[0])
            comp_id = cif.as_string(row[1])
            if asym_id not in chain_comp_ids:
                chain_comp_ids[asym_id] = set()
                chain_atom_counts[asym_id] = 0
            chain_comp_ids[asym_id].add(comp_id)
            chain_atom_counts[asym_id] += 1

    # Find orphan chains (in atom_site but not in struct_asym)
    atom_site_ids = set(chain_comp_ids.keys())
    orphan_ids = atom_site_ids - struct_asym_ids

    if not orphan_ids:
        return None

    # Build details for orphan chains
    details: dict[str, ChainDetails] = {}
    for chain_id in sorted(orphan_ids):
        details[chain_id] = ChainDetails(
            comp_ids=sorted(chain_comp_ids[chain_id]),
            atom_count=chain_atom_counts[chain_id],
        )

    return OrphanResult(
        pdb_id=pdb_id,
        file_path=cif_path,
        orphan_chains=sorted(orphan_ids),
        details=details,
    )


def _process_file(file_path: str) -> OrphanResult | None:
    """Wrapper for multiprocessing (accepts string path directly)."""
    return find_orphan_chains(file_path)


def enumerate_cif_files(mirror_path: Path) -> list[str]:
    """Enumerate all CIF files in a PDB mirror using gemmi.CifWalk.

    CifWalk automatically finds .cif and .cif.gz files, including the
    structure factor files (r????sf.ent.gz) from the wwPDB archive.

    Args:
        mirror_path: Root path of the PDB mirror.

    Returns:
        List of string paths for each CIF file found.
    """
    return list(gemmi.CifWalk(str(mirror_path)))


def scan_pdb_mirror(
    mirror_path: Path,
    workers: int = DEFAULT_WORKERS,
    file_list: list[Path] | None = None,
    quiet: bool = False,
) -> ScanResult:
    """Scan PDB mirror or specific files for orphan chains.

    Args:
        mirror_path: Root path of the PDB mirror (used if file_list is None).
        workers: Number of parallel workers (default: half of CPU cores, max 8).
        file_list: Optional list of specific files to scan.
        quiet: If True, suppress progress output (for JSON mode).

    Returns:
        ScanResult containing all findings.
    """
    # Collect file paths
    if file_list:
        files = [str(f) for f in file_list]
    else:
        if not quiet:
            with err_console.status("[bold blue]Enumerating CIF files..."):
                files = enumerate_cif_files(mirror_path)
            err_console.print(f"[green]Found {len(files):,} CIF files[/]")
        else:
            files = enumerate_cif_files(mirror_path)

    results: list[OrphanResult] = []

    # Use chunksize to reduce IPC overhead for large file counts
    chunksize = max(1, len(files) // (workers * 10))

    # Use multiprocessing.Pool.imap_unordered for efficient parallel processing
    with multiprocessing.Pool(processes=workers) as pool:
        if quiet:
            # Silent processing for JSON mode
            for result in pool.imap_unordered(_process_file, files, chunksize):
                if result is not None:
                    results.append(result)
        else:
            # Rich progress bar for interactive mode
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=err_console,
            ) as progress:
                task = progress.add_task("[cyan]Scanning files...", total=len(files))
                for result in pool.imap_unordered(_process_file, files, chunksize):
                    if result is not None:
                        results.append(result)
                    progress.update(task, advance=1)

    # Sort by PDB ID
    results.sort(key=lambda r: r.pdb_id)

    return ScanResult(
        scan_date=date.today().isoformat(),
        total_scanned=len(files),
        affected_entries=len(results),
        entries=results,
    )


def result_to_dict(result: ScanResult) -> dict:
    """Convert ScanResult to a JSON-serializable dictionary."""
    return {
        "scan_date": result.scan_date,
        "total_scanned": result.total_scanned,
        "affected_entries": result.affected_entries,
        "entries": [
            {
                "pdb_id": entry.pdb_id,
                "file_path": entry.file_path,
                "orphan_chains": entry.orphan_chains,
                "details": {
                    chain_id: {
                        "comp_ids": detail.comp_ids,
                        "atom_count": detail.atom_count,
                    }
                    for chain_id, detail in entry.details.items()
                },
            }
            for entry in result.entries
        ],
    }


def display_summary(result: ScanResult) -> None:
    """Display a rich summary of scan results."""
    # Summary panel
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

    # Results table (show first 20 entries if there are many)
    if result.entries:
        table = Table(title="Orphan Chains Found", show_lines=True)
        table.add_column("PDB ID", style="cyan", no_wrap=True)
        table.add_column("Orphan Chains", style="yellow")
        table.add_column("Components", style="green")
        table.add_column("Total Atoms", justify="right", style="magenta")

        display_entries = result.entries[:20]
        for entry in display_entries:
            chains_str = ", ".join(entry.orphan_chains)
            comps = set()
            total_atoms = 0
            for detail in entry.details.values():
                comps.update(detail.comp_ids)
                total_atoms += detail.atom_count
            comps_str = ", ".join(sorted(comps))
            table.add_row(entry.pdb_id.upper(), chains_str, comps_str, str(total_atoms))

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
) -> None:
    """Detect orphan chains in PDB CIF files.

    Scans CIF files to find chains that exist in _atom_site but are missing
    from _struct_asym. This indicates a data inconsistency in the PDB entry.

    [bold]Examples:[/]

        # Scan specific files
        [cyan]find-orphan-chains -f 2g10.cif.gz 1ts6.cif.gz[/]

        # Scan entire PDB mirror
        [cyan]find-orphan-chains -m /path/to/pdb/mirror -o results.json[/]

        # Output raw JSON only
        [cyan]find-orphan-chains -f 2g10.cif.gz --json[/]
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
        err_console.print(
            Panel(
                f"[bold]Workers:[/] {workers}\n[bold]Output:[/] {output or 'stdout'}",
                title="[bold green]Configuration",
                border_style="green",
            )
        )

    # Run scan
    if files:
        result = scan_pdb_mirror(
            mirror_path=Path("."),  # Not used when file_list is provided
            workers=workers,
            file_list=files,
            quiet=json_output,
        )
    else:
        assert mirror_path is not None
        result = scan_pdb_mirror(
            mirror_path=mirror_path,
            workers=workers,
            quiet=json_output,
        )

    # Output results
    output_dict = result_to_dict(result)
    json_str = json.dumps(output_dict, indent=2)

    if output:
        output.write_text(json_str)
        if not json_output:
            err_console.print(f"[green]Results written to {output}[/]")
    else:
        console.print(json_str)

    # Display summary
    if not json_output:
        display_summary(result)


if __name__ == "__main__":
    app()
