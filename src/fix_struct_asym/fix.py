"""Fix logic for missing struct_asym entries in CIF files."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

from gemmi import cif

from fix_struct_asym.core import (
    find_water_entity_id,
    get_atom_site_chain_info,
    get_next_entity_id,
)
from fix_struct_asym.find import detect_missing_asym_in_block
from fix_struct_asym.models import FixResult


def _create_water_entity(block: cif.Block, entity_id: str) -> None:
    """Create a water entity in the CIF block.

    Args:
        block: CIF data block.
        entity_id: Entity ID to use for water.
    """
    # Add to _entity loop
    entity_loop = block.find("_entity.", ["id", "type", "pdbx_description"])
    if entity_loop:
        # Find if loop exists, if so append to it
        entity_loop.append_row([entity_id, "water", "water"])
    else:
        # Create new loop
        loop = block.init_loop("_entity.", ["id", "type", "pdbx_description"])
        loop.add_row([entity_id, "water", "water"])


def _find_or_create_water_entity(block: cif.Block) -> str:
    """Find existing water entity or create a new one.

    Args:
        block: CIF data block.

    Returns:
        Entity ID for water.
    """
    water_entity_id = find_water_entity_id(block)
    if water_entity_id:
        return water_entity_id

    # Create new water entity
    new_entity_id = get_next_entity_id(block)
    _create_water_entity(block, new_entity_id)
    return new_entity_id


def _add_to_struct_asym(block: cif.Block, asym_ids: list[str], entity_id: str) -> None:
    """Add asym IDs to _struct_asym loop.

    Args:
        block: CIF data block.
        asym_ids: List of asym IDs to add.
        entity_id: Entity ID to associate with the entries.
    """
    struct_asym = block.find("_struct_asym.", ["id", "entity_id"])
    if struct_asym:
        for asym_id in asym_ids:
            struct_asym.append_row([asym_id, entity_id])
    else:
        # Create new loop
        loop = block.init_loop("_struct_asym.", ["id", "entity_id"])
        for asym_id in asym_ids:
            loop.add_row([asym_id, entity_id])


def fix_missing_struct_asym(
    cif_path: str | Path,
    output_path: str | Path | None = None,
    backup: bool = False,
) -> FixResult:
    """Fix missing struct_asym entries by adding them.

    All missing struct_asym entries in known PDB entries are water (HOH),
    so they are assigned to the water entity.

    Args:
        cif_path: Path to the input CIF file (handles .gz automatically).
        output_path: Path for output file. If None, uses cif_path (in-place).
        backup: If True and modifying in-place, create a .bak backup.

    Returns:
        FixResult with details of the fix operation.
    """
    cif_path = Path(cif_path)
    input_path_str = str(cif_path)

    # Determine output path
    if output_path is None:
        output_path = cif_path
    else:
        output_path = Path(output_path)

    # Read CIF
    try:
        doc = cif.read(input_path_str)
    except (RuntimeError, OSError) as e:
        return FixResult(
            pdb_id="",
            input_path=input_path_str,
            output_path=str(output_path),
            success=False,
            asym_ids_fixed=[],
            error=f"Error reading file: {e}",
        )

    if len(doc) == 0:
        return FixResult(
            pdb_id="",
            input_path=input_path_str,
            output_path=str(output_path),
            success=False,
            asym_ids_fixed=[],
            error="Empty CIF document",
        )

    block = doc[0]
    pdb_id = block.name.lower()

    # Find missing struct_asym entries
    missing_ids = detect_missing_asym_in_block(block)

    if not missing_ids:
        return FixResult(
            pdb_id=pdb_id,
            input_path=input_path_str,
            output_path=str(output_path),
            success=True,
            asym_ids_fixed=[],
        )

    # Verify all missing entries are water (HOH)
    chain_comp_ids, _ = get_atom_site_chain_info(block)
    for asym_id in missing_ids:
        comp_ids = chain_comp_ids.get(asym_id, set())
        if comp_ids != {"HOH"}:
            return FixResult(
                pdb_id=pdb_id,
                input_path=input_path_str,
                output_path=str(output_path),
                success=False,
                asym_ids_fixed=[],
                error=f"Missing asym {asym_id} has non-water components: {comp_ids}",
            )

    # Find or create water entity
    water_entity_id = _find_or_create_water_entity(block)

    # Add missing entries to _struct_asym
    _add_to_struct_asym(block, missing_ids, water_entity_id)

    # Create backup if requested and modifying in-place
    if backup and output_path == cif_path:
        backup_path = cif_path.with_suffix(cif_path.suffix + ".bak")
        shutil.copy2(cif_path, backup_path)

    # Write output
    try:
        output_path_str = str(output_path)

        # Handle gzip output
        if output_path_str.endswith(".gz"):
            # Write to uncompressed temp, then compress
            temp_path = output_path.with_suffix("")
            doc.write_file(str(temp_path))
            with open(temp_path, "rb") as f_in:
                with gzip.open(output_path_str, "wb") as f_out:
                    f_out.write(f_in.read())
            temp_path.unlink()
        else:
            doc.write_file(output_path_str)

    except (OSError, RuntimeError) as e:
        return FixResult(
            pdb_id=pdb_id,
            input_path=input_path_str,
            output_path=str(output_path),
            success=False,
            asym_ids_fixed=[],
            error=f"Error writing file: {e}",
        )

    return FixResult(
        pdb_id=pdb_id,
        input_path=input_path_str,
        output_path=str(output_path),
        success=True,
        asym_ids_fixed=missing_ids,
        water_entity_id=water_entity_id,
    )
