"""Detection logic for missing struct_asym entries in CIF files."""

from __future__ import annotations

import multiprocessing
import random
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from gemmi import cif

from fix_struct_asym.core import (
    enumerate_cif_files,
    get_atom_site_chain_info,
    get_struct_asym_ids,
    read_cif,
)
from fix_struct_asym.models import AsymDetails, MissingAsymResult, ScanResult

if TYPE_CHECKING:
    from collections.abc import Callable


def find_missing_struct_asym(cif_path: str) -> MissingAsymResult | None:
    """Detect missing struct_asym entries in a single CIF file.

    Args:
        cif_path: Path to the CIF file to analyze (handles .gz automatically).

    Returns:
        MissingAsymResult if missing entries are found, None otherwise.
    """
    doc = read_cif(cif_path)
    if doc is None:
        return None

    # Explicit length check for empty document
    if len(doc) == 0:
        return None

    block = doc[0]
    pdb_id = block.name.lower()

    # Extract chain IDs from _struct_asym
    struct_asym_ids = get_struct_asym_ids(block)

    # Extract chain info from _atom_site
    chain_comp_ids, chain_atom_counts = get_atom_site_chain_info(block)

    # Find missing asym IDs (in atom_site but not in struct_asym)
    atom_site_ids = set(chain_comp_ids.keys())
    missing_ids = atom_site_ids - struct_asym_ids

    if not missing_ids:
        return None

    # Build details for missing asym IDs
    details: dict[str, AsymDetails] = {}
    for asym_id in sorted(missing_ids):
        details[asym_id] = AsymDetails(
            comp_ids=sorted(chain_comp_ids[asym_id]),
            atom_count=chain_atom_counts[asym_id],
        )

    return MissingAsymResult(
        pdb_id=pdb_id,
        file_path=cif_path,
        missing_asym_ids=sorted(missing_ids),
        details=details,
    )


def detect_missing_asym_in_block(block: cif.Block) -> list[str]:
    """Detect missing struct_asym entries in a CIF block.

    Args:
        block: CIF data block.

    Returns:
        List of missing asym IDs.
    """
    struct_asym_ids = get_struct_asym_ids(block)
    chain_comp_ids, _ = get_atom_site_chain_info(block)
    atom_site_ids = set(chain_comp_ids.keys())
    return sorted(atom_site_ids - struct_asym_ids)


def _process_file(file_path: str) -> MissingAsymResult | None:
    """Wrapper for multiprocessing (accepts string path directly)."""
    return find_missing_struct_asym(file_path)


def scan_pdb_mirror(
    mirror_path: Path,
    workers: int = 4,
    file_list: list[Path] | None = None,
    quiet: bool = False,
    limit: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ScanResult:
    """Scan PDB mirror or specific files for missing struct_asym entries.

    Args:
        mirror_path: Root path of the PDB mirror (used if file_list is None).
        workers: Number of parallel workers.
        file_list: Optional list of specific files to scan.
        quiet: If True, suppress progress output.
        limit: If set, randomly sample this many files from the total.
        progress_callback: Optional callback(current, total) for progress updates.

    Returns:
        ScanResult containing all findings.
    """
    # Collect file paths
    if file_list:
        files = [str(f) for f in file_list]
    else:
        files = enumerate_cif_files(mirror_path)

    # Apply limit if specified (random sample)
    if limit is not None and limit < len(files):
        files = random.sample(files, limit)

    results: list[MissingAsymResult] = []

    # Use multiprocessing.Pool.imap_unordered for efficient parallel processing
    with multiprocessing.Pool(processes=workers) as pool:
        for i, result in enumerate(pool.imap_unordered(_process_file, files)):
            if result is not None:
                results.append(result)
            if progress_callback:
                progress_callback(i + 1, len(files))

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
                "missing_asym_ids": entry.missing_asym_ids,
                "details": {
                    asym_id: {
                        "comp_ids": detail.comp_ids,
                        "atom_count": detail.atom_count,
                    }
                    for asym_id, detail in entry.details.items()
                },
            }
            for entry in result.entries
        ],
    }
