"""Core CIF manipulation utilities."""

from __future__ import annotations

from pathlib import Path

import gemmi
from gemmi import cif


def read_cif(path: str | Path) -> cif.Document | None:
    """Read a CIF file safely.

    Args:
        path: Path to the CIF file (handles .gz automatically).

    Returns:
        CIF document or None if reading fails.
    """
    try:
        return cif.read(str(path))
    except (RuntimeError, OSError):
        return None


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


def get_struct_asym_ids(block: cif.Block) -> set[str]:
    """Extract chain IDs from _struct_asym category.

    Args:
        block: CIF data block.

    Returns:
        Set of chain IDs (asym_id values).
    """
    struct_asym_ids: set[str] = set()
    struct_asym = block.find("_struct_asym.", ["id"])
    if struct_asym:
        for row in struct_asym:
            struct_asym_ids.add(cif.as_string(row[0]))
    return struct_asym_ids


def get_atom_site_chain_info(
    block: cif.Block,
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """Extract chain info from _atom_site category.

    Args:
        block: CIF data block.

    Returns:
        Tuple of (chain_comp_ids, chain_atom_counts) where:
            - chain_comp_ids: mapping from chain_id to set of component IDs
            - chain_atom_counts: mapping from chain_id to atom count
    """
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

    return chain_comp_ids, chain_atom_counts


def find_water_entity_id(block: cif.Block) -> str | None:
    """Find the entity ID for water (HOH) in the CIF block.

    Args:
        block: CIF data block.

    Returns:
        Entity ID for water or None if not found.
    """
    entity_poly_type = block.find("_entity.", ["id", "type"])
    if not entity_poly_type:
        return None

    for row in entity_poly_type:
        entity_id = cif.as_string(row[0])
        entity_type = cif.as_string(row[1])
        if entity_type == "water":
            return entity_id

    return None


def get_next_entity_id(block: cif.Block) -> str:
    """Get the next available entity ID.

    Args:
        block: CIF data block.

    Returns:
        Next entity ID as string (max existing + 1).
    """
    max_id = 0
    entity = block.find("_entity.", ["id"])
    if entity:
        for row in entity:
            try:
                entity_id = int(cif.as_string(row[0]))
                max_id = max(max_id, entity_id)
            except ValueError:
                continue
    return str(max_id + 1)
