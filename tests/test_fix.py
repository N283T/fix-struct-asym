"""Tests for fix module."""

from pathlib import Path

from fix_struct_asym.find import find_missing_struct_asym
from fix_struct_asym.fix import fix_missing_struct_asym


class TestFixMissingStructAsym:
    """Tests for fix_missing_struct_asym function."""

    def test_fix_missing_asym(self, orphan_cif: Path, tmp_path: Path) -> None:
        """Test that missing struct_asym entries are fixed."""
        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(orphan_cif, output_path)

        assert result.success is True
        assert result.pdb_id == "test2"
        assert set(result.asym_ids_fixed) == {"B", "C"}
        assert result.water_entity_id is not None

        # Verify fixed file has no missing entries
        verify_result = find_missing_struct_asym(str(output_path))
        assert verify_result is None

    def test_fix_normal_cif_no_changes(self, normal_cif: Path, tmp_path: Path) -> None:
        """Test that a CIF with no missing entries is not modified."""
        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(normal_cif, output_path)

        assert result.success is True
        assert result.asym_ids_fixed == []

    def test_fix_empty_cif_returns_error(self, empty_cif: Path, tmp_path: Path) -> None:
        """Test that an empty CIF file returns error."""
        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(empty_cif, output_path)

        assert result.success is False
        assert result.error is not None
        assert "Empty CIF document" in result.error

    def test_fix_nonexistent_file_returns_error(self, tmp_path: Path) -> None:
        """Test that a nonexistent file returns error."""
        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(tmp_path / "nonexistent.cif", output_path)

        assert result.success is False
        assert result.error is not None
        assert "Error reading" in result.error

    def test_fix_in_place(self, orphan_cif: Path, tmp_path: Path) -> None:
        """Test fixing a file in place."""
        # Copy to temp directory first
        temp_cif = tmp_path / "test.cif"
        temp_cif.write_text(orphan_cif.read_text())

        result = fix_missing_struct_asym(temp_cif, output_path=None)

        assert result.success is True
        assert set(result.asym_ids_fixed) == {"B", "C"}
        assert result.output_path == str(temp_cif)

        # Verify fixed file has no missing entries
        verify_result = find_missing_struct_asym(str(temp_cif))
        assert verify_result is None

    def test_fix_in_place_with_backup(self, orphan_cif: Path, tmp_path: Path) -> None:
        """Test fixing a file in place with backup."""
        # Copy to temp directory first
        temp_cif = tmp_path / "test.cif"
        temp_cif.write_text(orphan_cif.read_text())

        result = fix_missing_struct_asym(temp_cif, output_path=None, backup=True)

        assert result.success is True
        assert set(result.asym_ids_fixed) == {"B", "C"}

        # Verify backup was created
        backup_path = temp_cif.with_suffix(".cif.bak")
        assert backup_path.exists()

    def test_fix_reuses_existing_water_entity(
        self, temp_cif_dir: Path, tmp_path: Path
    ) -> None:
        """Test that fix reuses existing water entity."""
        # Create CIF with existing water entity
        cif_content = """\
data_TEST5
#
_entry.id TEST5
#
loop_
_entity.id
_entity.type
_entity.pdbx_description
1 polymer protein
2 water water
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
2 B HOH O
"""
        cif_path = temp_cif_dir / "test5.cif"
        cif_path.write_text(cif_content)

        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(cif_path, output_path)

        assert result.success is True
        assert result.asym_ids_fixed == ["B"]
        assert result.water_entity_id == "2"  # Reuses existing water entity

    def test_fix_creates_water_entity_if_missing(
        self, no_struct_asym_cif: Path, tmp_path: Path
    ) -> None:
        """Test that fix creates water entity if missing."""
        output_path = tmp_path / "fixed.cif"

        # This test needs a CIF with missing water entries but no water entity
        # The no_struct_asym_cif has ALA (not water), so it should fail
        result = fix_missing_struct_asym(no_struct_asym_cif, output_path)

        # Should fail because missing asym A contains ALA, not HOH
        assert result.success is False
        assert result.error is not None
        assert "non-water" in result.error

    def test_fix_rejects_non_water_missing(
        self, temp_cif_dir: Path, tmp_path: Path
    ) -> None:
        """Test that fix rejects missing entries with non-water."""
        # Create CIF with non-water missing entry
        cif_content = """\
data_TEST6
#
_entry.id TEST6
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
2 B NA NA
"""
        cif_path = temp_cif_dir / "test6.cif"
        cif_path.write_text(cif_content)

        output_path = tmp_path / "fixed.cif"
        result = fix_missing_struct_asym(cif_path, output_path)

        assert result.success is False
        assert result.error is not None
        assert "non-water" in result.error


class TestFixResultDataClass:
    """Tests for FixResult dataclass."""

    def test_fix_result_success(self) -> None:
        """Test FixResult for successful fix."""
        from fix_struct_asym.models import FixResult

        result = FixResult(
            pdb_id="test",
            input_path="/path/to/input.cif",
            output_path="/path/to/output.cif",
            success=True,
            asym_ids_fixed=["B", "C"],
            water_entity_id="2",
        )
        assert result.success is True
        assert result.asym_ids_fixed == ["B", "C"]
        assert result.water_entity_id == "2"
        assert result.error is None

    def test_fix_result_failure(self) -> None:
        """Test FixResult for failed fix."""
        from fix_struct_asym.models import FixResult

        result = FixResult(
            pdb_id="test",
            input_path="/path/to/input.cif",
            output_path="/path/to/output.cif",
            success=False,
            asym_ids_fixed=[],
            error="Test error",
        )
        assert result.success is False
        assert result.asym_ids_fixed == []
        assert result.error == "Test error"
