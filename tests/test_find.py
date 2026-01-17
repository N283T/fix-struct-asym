"""Tests for find module."""

from pathlib import Path

from fix_struct_asym import AsymDetails, MissingAsymResult, ScanResult
from fix_struct_asym.find import (
    find_missing_struct_asym,
    result_to_dict,
    scan_pdb_mirror,
)


class TestFindMissingStructAsym:
    """Tests for find_missing_struct_asym function."""

    def test_normal_cif_no_missing(self, normal_cif: Path) -> None:
        """Test that a CIF with all entries in _struct_asym returns None."""
        result = find_missing_struct_asym(str(normal_cif))
        assert result is None

    def test_missing_asym_detected(self, orphan_cif: Path) -> None:
        """Test that missing struct_asym entries are detected."""
        result = find_missing_struct_asym(str(orphan_cif))

        assert result is not None
        assert result.pdb_id == "test2"
        assert result.missing_asym_ids == ["B", "C"]
        assert "B" in result.details
        assert "C" in result.details
        assert result.details["B"].comp_ids == ["HOH"]
        assert result.details["B"].atom_count == 2
        assert result.details["C"].comp_ids == ["HOH"]
        assert result.details["C"].atom_count == 1

    def test_empty_cif_returns_none(self, empty_cif: Path) -> None:
        """Test that an empty CIF file returns None."""
        result = find_missing_struct_asym(str(empty_cif))
        assert result is None

    def test_no_struct_asym_all_missing(self, no_struct_asym_cif: Path) -> None:
        """Test that missing _struct_asym makes all entries missing."""
        result = find_missing_struct_asym(str(no_struct_asym_cif))

        assert result is not None
        assert result.missing_asym_ids == ["A", "B"]

    def test_no_atom_site_returns_none(self, no_atom_site_cif: Path) -> None:
        """Test that missing _atom_site returns None (no atoms to check)."""
        result = find_missing_struct_asym(str(no_atom_site_cif))
        assert result is None

    def test_nonexistent_file_returns_none(self, temp_cif_dir: Path) -> None:
        """Test that a nonexistent file returns None with warning."""
        result = find_missing_struct_asym(str(temp_cif_dir / "nonexistent.cif"))
        assert result is None


class TestScanPdbMirror:
    """Tests for scan_pdb_mirror function."""

    def test_scan_single_file(self, orphan_cif: Path) -> None:
        """Test scanning a single file."""
        result = scan_pdb_mirror(
            mirror_path=Path("."),
            workers=1,
            file_list=[orphan_cif],
            quiet=True,
        )

        assert result.total_scanned == 1
        assert result.affected_entries == 1
        assert len(result.entries) == 1
        assert result.entries[0].pdb_id == "test2"

    def test_scan_multiple_files(
        self, normal_cif: Path, orphan_cif: Path, no_atom_site_cif: Path
    ) -> None:
        """Test scanning multiple files."""
        result = scan_pdb_mirror(
            mirror_path=Path("."),
            workers=1,
            file_list=[normal_cif, orphan_cif, no_atom_site_cif],
            quiet=True,
        )

        assert result.total_scanned == 3
        assert result.affected_entries == 1  # Only orphan_cif has missing entries
        assert result.entries[0].pdb_id == "test2"

    def test_scan_empty_list(self) -> None:
        """Test scanning an empty file list."""
        result = scan_pdb_mirror(
            mirror_path=Path("."),
            workers=1,
            file_list=[],
            quiet=True,
        )

        assert result.total_scanned == 0
        assert result.affected_entries == 0
        assert result.entries == []

    def test_scan_with_limit(
        self, normal_cif: Path, orphan_cif: Path, no_atom_site_cif: Path
    ) -> None:
        """Test scanning with limit option."""
        result = scan_pdb_mirror(
            mirror_path=Path("."),
            workers=1,
            file_list=[normal_cif, orphan_cif, no_atom_site_cif],
            quiet=True,
            limit=2,
        )

        # With limit=2, only 2 files should be scanned
        assert result.total_scanned == 2


class TestResultToDict:
    """Tests for result_to_dict function."""

    def test_empty_result(self) -> None:
        """Test converting an empty result."""
        result = ScanResult(
            scan_date="2026-01-17",
            total_scanned=0,
            affected_entries=0,
            entries=[],
        )
        d = result_to_dict(result)

        assert d["scan_date"] == "2026-01-17"
        assert d["total_scanned"] == 0
        assert d["affected_entries"] == 0
        assert d["entries"] == []

    def test_result_with_entries(self) -> None:
        """Test converting a result with entries."""
        result = ScanResult(
            scan_date="2026-01-17",
            total_scanned=10,
            affected_entries=1,
            entries=[
                MissingAsymResult(
                    pdb_id="test1",
                    file_path="/path/to/test1.cif",
                    missing_asym_ids=["B", "C"],
                    details={
                        "B": AsymDetails(comp_ids=["HOH"], atom_count=5),
                        "C": AsymDetails(comp_ids=["HOH", "NA"], atom_count=3),
                    },
                )
            ],
        )
        d = result_to_dict(result)

        assert d["total_scanned"] == 10
        assert d["affected_entries"] == 1
        assert len(d["entries"]) == 1

        entry = d["entries"][0]
        assert entry["pdb_id"] == "test1"
        assert entry["missing_asym_ids"] == ["B", "C"]
        assert entry["details"]["B"]["comp_ids"] == ["HOH"]
        assert entry["details"]["B"]["atom_count"] == 5
        assert entry["details"]["C"]["comp_ids"] == ["HOH", "NA"]


class TestDataClasses:
    """Tests for data classes."""

    def test_asym_details(self) -> None:
        """Test AsymDetails dataclass."""
        details = AsymDetails(comp_ids=["HOH", "NA"], atom_count=10)
        assert details.comp_ids == ["HOH", "NA"]
        assert details.atom_count == 10

    def test_missing_asym_result_defaults(self) -> None:
        """Test MissingAsymResult dataclass default values."""
        result = MissingAsymResult(
            pdb_id="test",
            file_path="/path/to/test.cif",
            missing_asym_ids=["A"],
        )
        assert result.details == {}

    def test_scan_result(self) -> None:
        """Test ScanResult dataclass."""
        result = ScanResult(
            scan_date="2026-01-17",
            total_scanned=100,
            affected_entries=5,
            entries=[],
        )
        assert result.scan_date == "2026-01-17"
        assert result.total_scanned == 100
        assert result.affected_entries == 5
