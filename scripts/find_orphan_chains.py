#!/usr/bin/env python3
"""Detect PDB entries where chains exist in _atom_site but not in _struct_asym.

This script scans CIF files to find "orphan chains" - chains that are present
in the _atom_site category but missing from the _struct_asym category.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import gemmi
from gemmi import cif
from tqdm import tqdm

if TYPE_CHECKING:
    from collections.abc import Iterator

# Default number of workers: use half of CPU cores, minimum 1, maximum 8
DEFAULT_WORKERS = min(8, max(1, (os.cpu_count() or 4) // 2))


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
    except Exception as e:
        print(f"Error reading {cif_path}: {e}", file=sys.stderr)
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


def enumerate_cif_files(mirror_path: Path) -> Iterator[str]:
    """Enumerate all CIF files in a PDB mirror using gemmi.CifWalk.

    CifWalk automatically finds .cif and .cif.gz files, including the
    structure factor files (r????sf.ent.gz) from the wwPDB archive.

    Args:
        mirror_path: Root path of the PDB mirror.

    Yields:
        String paths for each CIF file found.
    """
    yield from gemmi.CifWalk(str(mirror_path))


def scan_pdb_mirror(
    mirror_path: Path,
    workers: int = DEFAULT_WORKERS,
    file_list: list[Path] | None = None,
) -> ScanResult:
    """Scan PDB mirror or specific files for orphan chains.

    Args:
        mirror_path: Root path of the PDB mirror (used if file_list is None).
        workers: Number of parallel workers (default: half of CPU cores, max 8).
        file_list: Optional list of specific files to scan.

    Returns:
        ScanResult containing all findings.
    """
    # Collect file paths
    if file_list:
        files = [str(f) for f in file_list]
    else:
        print("Enumerating CIF files...", file=sys.stderr)
        files = list(enumerate_cif_files(mirror_path))
        print(f"Found {len(files)} CIF files", file=sys.stderr)

    results: list[OrphanResult] = []

    # Use chunksize to reduce IPC overhead for large file counts
    chunksize = max(1, len(files) // (workers * 10))

    # Use multiprocessing.Pool.imap_unordered for efficient parallel processing
    with multiprocessing.Pool(processes=workers) as pool:
        with tqdm(total=len(files), desc="Scanning", unit="file") as pbar:
            for result in pool.imap_unordered(_process_file, files, chunksize):
                if result is not None:
                    results.append(result)
                pbar.update(1)

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


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect orphan chains in PDB CIF files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan entire PDB mirror
  %(prog)s --mirror-path /path/to/pdb/mirror --output results.json

  # Scan specific files
  %(prog)s --files 2g10.cif 1ts6.cif 2k9y.cif --output results.json

  # Print to stdout
  %(prog)s --files 2g10.cif
        """,
    )

    parser.add_argument(
        "--mirror-path",
        type=Path,
        help="Path to PDB mirror root directory",
    )
    parser.add_argument(
        "--files",
        type=Path,
        nargs="+",
        help="Specific CIF files to scan",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output JSON file (default: stdout)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of parallel workers (default: {DEFAULT_WORKERS})",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.mirror_path and not args.files:
        parser.error("Either --mirror-path or --files must be specified")

    if args.mirror_path and args.files:
        parser.error("Cannot specify both --mirror-path and --files")

    # Run scan
    if args.files:
        # Verify files exist
        missing = [f for f in args.files if not f.exists()]
        if missing:
            print(f"Error: Files not found: {missing}", file=sys.stderr)
            return 1

        result = scan_pdb_mirror(
            mirror_path=Path("."),  # Not used when file_list is provided
            workers=args.workers,
            file_list=args.files,
        )
    else:
        if not args.mirror_path.is_dir():
            print(
                f"Error: Mirror path does not exist: {args.mirror_path}",
                file=sys.stderr,
            )
            return 1

        result = scan_pdb_mirror(
            mirror_path=args.mirror_path,
            workers=args.workers,
        )

    # Output results
    output_dict = result_to_dict(result)
    json_str = json.dumps(output_dict, indent=2)

    if args.output:
        args.output.write_text(json_str)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(json_str)

    # Summary
    print(
        f"\nSummary: {result.affected_entries} affected entries "
        f"out of {result.total_scanned} scanned",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
