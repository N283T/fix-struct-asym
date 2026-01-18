#!/usr/bin/env python3
"""CLI for fixing missing struct_asym entries in PDB CIF files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel
from rich.table import Table

from fix_struct_asym.cli._common import console, create_progress, err_console
from fix_struct_asym.fix import fix_missing_struct_asym
from fix_struct_asym.models import FixResult

app = typer.Typer(
    name="fix-missing-struct-asym",
    help="Fix missing _struct_asym entries in PDB CIF files.",
    add_completion=False,
    rich_markup_mode="rich",
)


def _load_results_json(results_path: Path) -> list[dict]:
    """Load entries from a find-missing-struct-asym results JSON file.

    Args:
        results_path: Path to the JSON file.

    Returns:
        List of entry dicts with pdb_id, file_path, missing_asym_ids.
    """
    with open(results_path) as f:
        data = json.load(f)

    return data.get("entries", [])


def display_results(results: list[FixResult], quiet: bool = False) -> None:
    """Display fix results summary.

    Args:
        results: List of FixResult objects.
        quiet: If True, suppress output.
    """
    if quiet:
        return

    success_count = sum(1 for r in results if r.success and r.asym_ids_fixed)
    skip_count = sum(1 for r in results if r.success and not r.asym_ids_fixed)
    fail_count = sum(1 for r in results if not r.success)

    summary_text = (
        f"[bold]Total Processed:[/] {len(results)}\n"
        f"[bold]Fixed:[/] [green]{success_count}[/]\n"
        f"[bold]Skipped (no missing):[/] [yellow]{skip_count}[/]\n"
        f"[bold]Failed:[/] [red]{fail_count}[/]"
    )

    err_console.print(
        Panel(summary_text, title="[bold blue]Fix Summary", border_style="blue")
    )

    # Show fixed entries
    fixed_results = [r for r in results if r.success and r.asym_ids_fixed]
    if fixed_results:
        table = Table(title="Fixed Entries", show_lines=True)
        table.add_column("PDB ID", style="cyan", no_wrap=True)
        table.add_column("Asym IDs Fixed", style="green")
        table.add_column("Water Entity", style="magenta")
        table.add_column("Output", style="dim")

        display_entries = fixed_results[:20]
        for result in display_entries:
            table.add_row(
                result.pdb_id.upper(),
                ", ".join(result.asym_ids_fixed),
                result.water_entity_id or "-",
                str(Path(result.output_path).name),
            )

        if len(fixed_results) > 20:
            table.add_row(
                f"... and {len(fixed_results) - 20} more",
                "",
                "",
                "",
                style="dim",
            )

        err_console.print(table)

    # Show failures
    failed_results = [r for r in results if not r.success]
    if failed_results:
        err_console.print("\n[bold red]Failures:[/]")
        for result in failed_results[:10]:
            err_console.print(
                f"  [red]{result.pdb_id or result.input_path}:[/] {result.error}"
            )
        if len(failed_results) > 10:
            err_console.print(f"  ... and {len(failed_results) - 10} more failures")


@app.command()
def main(
    input_json: Annotated[
        Path | None,
        typer.Option(
            "--input",
            "-i",
            help="Input JSON file from find-missing-struct-asym",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    files: Annotated[
        list[Path] | None,
        typer.Option(
            "--files",
            "-f",
            help="Specific CIF files to fix",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output directory for fixed files",
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    in_place: Annotated[
        bool,
        typer.Option(
            "--in-place",
            help="Modify files in place",
        ),
    ] = False,
    backup: Annotated[
        bool,
        typer.Option(
            "--backup",
            help="Create .bak backup when modifying in place",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            "-j",
            help="Output results as JSON",
        ),
    ] = False,
) -> None:
    """Fix missing struct_asym entries in PDB CIF files.

    Adds missing entries to _struct_asym by associating them with the water entity.
    All known missing struct_asym entries in PDB are water (HOH).

    [bold]Examples:[/]

        # Fix files from find-missing-struct-asym results
        [cyan]fix-missing-struct-asym -i results.json -o ./fixed/[/]

        # Fix specific files
        [cyan]fix-missing-struct-asym -f 2g10.cif.gz -o ./fixed/[/]

        # Fix in place with backup
        [cyan]fix-missing-struct-asym -f 2g10.cif.gz --in-place --backup[/]
    """
    # Validate arguments
    if input_json is None and files is None:
        err_console.print("[red]Error:[/] Either --input or --files must be specified")
        raise typer.Exit(code=1)

    if input_json is not None and files is not None:
        err_console.print("[red]Error:[/] Cannot specify both --input and --files")
        raise typer.Exit(code=1)

    if not in_place and output_dir is None:
        err_console.print(
            "[red]Error:[/] Either --output or --in-place must be specified"
        )
        raise typer.Exit(code=1)

    if in_place and output_dir is not None:
        err_console.print("[red]Error:[/] Cannot specify both --output and --in-place")
        raise typer.Exit(code=1)

    # Create output directory if needed
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Collect files to process
    file_paths: list[Path]
    if files:
        file_paths = files
    else:
        assert input_json is not None
        entries = _load_results_json(input_json)
        file_paths = [Path(e["file_path"]) for e in entries]

    if not file_paths:
        err_console.print("[yellow]No files to process[/]")
        raise typer.Exit(code=0)

    # Show configuration
    if not json_output:
        config_text = f"[bold]Files:[/] {len(file_paths)}"
        if in_place:
            config_text += "\n[bold]Mode:[/] In-place"
            if backup:
                config_text += " (with backup)"
        else:
            config_text += f"\n[bold]Output:[/] {output_dir}"
        err_console.print(
            Panel(config_text, title="[bold green]Configuration", border_style="green")
        )

    # Process files
    results: list[FixResult] = []

    if json_output:
        for file_path in file_paths:
            output_path = output_dir / file_path.name if output_dir else None
            result = fix_missing_struct_asym(file_path, output_path, backup=backup)
            results.append(result)
    else:
        with create_progress() as progress:
            task = progress.add_task("[cyan]Fixing files...", total=len(file_paths))
            for file_path in file_paths:
                output_path = output_dir / file_path.name if output_dir else None
                result = fix_missing_struct_asym(file_path, output_path, backup=backup)
                results.append(result)
                progress.update(task, advance=1)

    # Output results
    if json_output:
        output_dict = {
            "total": len(results),
            "fixed": sum(1 for r in results if r.success and r.asym_ids_fixed),
            "skipped": sum(1 for r in results if r.success and not r.asym_ids_fixed),
            "failed": sum(1 for r in results if not r.success),
            "results": [
                {
                    "pdb_id": r.pdb_id,
                    "input_path": r.input_path,
                    "output_path": r.output_path,
                    "success": r.success,
                    "asym_ids_fixed": r.asym_ids_fixed,
                    "water_entity_id": r.water_entity_id,
                    "error": r.error,
                }
                for r in results
            ],
        }
        console.print(json.dumps(output_dict, indent=2))
    else:
        display_results(results)

    # Exit with error code if any failures
    if any(not r.success for r in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
