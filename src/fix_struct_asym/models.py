"""Data models for fix_struct_asym."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AsymDetails:
    """Details about a missing struct_asym entry."""

    comp_ids: list[str]
    atom_count: int


@dataclass
class MissingAsymResult:
    """Result of missing struct_asym detection for a single file."""

    pdb_id: str
    file_path: str
    missing_asym_ids: list[str]
    details: dict[str, AsymDetails] = field(default_factory=dict)


@dataclass
class ScanResult:
    """Result of scanning multiple files."""

    scan_date: str
    total_scanned: int
    affected_entries: int
    entries: list[MissingAsymResult]


@dataclass
class FixResult:
    """Result of fixing missing struct_asym entries in a single file."""

    pdb_id: str
    input_path: str
    output_path: str
    success: bool
    asym_ids_fixed: list[str]
    water_entity_id: str | None = None
    error: str | None = None
