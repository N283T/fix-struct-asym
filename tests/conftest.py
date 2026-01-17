"""Pytest fixtures for find_orphan_chains tests."""

from pathlib import Path

import pytest


@pytest.fixture
def temp_cif_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for CIF files."""
    return tmp_path


@pytest.fixture
def normal_cif(temp_cif_dir: Path) -> Path:
    """Create a CIF file with no orphan chains (all chains in _struct_asym)."""
    cif_content = """\
data_TEST1
#
_entry.id TEST1
#
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 2
#
loop_
_atom_site.id
_atom_site.label_asym_id
_atom_site.label_comp_id
_atom_site.label_atom_id
1 A ALA CA
2 A ALA CB
3 B HOH O
"""
    cif_path = temp_cif_dir / "test1.cif"
    cif_path.write_text(cif_content)
    return cif_path


@pytest.fixture
def orphan_cif(temp_cif_dir: Path) -> Path:
    """Create a CIF file with orphan chains (chains not in _struct_asym)."""
    cif_content = """\
data_TEST2
#
_entry.id TEST2
#
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
#
loop_
_atom_site.id
_atom_site.label_asym_id
_atom_site.label_comp_id
_atom_site.label_atom_id
1 A ALA CA
2 A ALA CB
3 B HOH O
4 B HOH O
5 C HOH O
"""
    cif_path = temp_cif_dir / "test2.cif"
    cif_path.write_text(cif_content)
    return cif_path


@pytest.fixture
def empty_cif(temp_cif_dir: Path) -> Path:
    """Create an empty CIF file."""
    cif_path = temp_cif_dir / "empty.cif"
    cif_path.write_text("")
    return cif_path


@pytest.fixture
def no_struct_asym_cif(temp_cif_dir: Path) -> Path:
    """Create a CIF file with no _struct_asym category."""
    cif_content = """\
data_TEST3
#
_entry.id TEST3
#
loop_
_atom_site.id
_atom_site.label_asym_id
_atom_site.label_comp_id
_atom_site.label_atom_id
1 A ALA CA
2 B HOH O
"""
    cif_path = temp_cif_dir / "test3.cif"
    cif_path.write_text(cif_content)
    return cif_path


@pytest.fixture
def no_atom_site_cif(temp_cif_dir: Path) -> Path:
    """Create a CIF file with no _atom_site category."""
    cif_content = """\
data_TEST4
#
_entry.id TEST4
#
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 2
"""
    cif_path = temp_cif_dir / "test4.cif"
    cif_path.write_text(cif_content)
    return cif_path
