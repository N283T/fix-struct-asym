# fix-struct-asym

Detect and fix `_struct_asym` inconsistencies in PDB mmCIF files.

## Reports

- [English Report](reports/report.md)
- [日本語レポート](reports/report_jp.md)

## Background

During analysis of the PDB archive, we discovered a data inconsistency where certain entries contain `_atom_site.label_asym_id` values that lack corresponding entries in the `_struct_asym` category. According to the mmCIF dictionary, every chain referenced in `_atom_site` should have a matching definition in `_struct_asym`.

A systematic scan of **243,083 PDB entries** identified **3 affected entries**:

| Date | Source | Action |
|------|--------|--------|
| 2025-10-10 | PDB mirror | Mirror sync |
| 2026-01-17 | PDB mirror | Full archive scan (243,083 entries) |
| 2026-01-18 | RCSB | Verification of affected entries |

**Affected entries:**

| PDB ID | Missing Asym ID(s) | Component | Atom Count |
|--------|-------------------|-----------|------------|
| 1TS6   | C                 | HOH       | 7          |
| 2G10   | F                 | HOH       | 147        |
| 2K9Y   | C, D              | HOH       | 12         |

All cases involve water molecule chains (HOH) that exist in atom records but are missing from `_struct_asym`.

## Installation

```bash
pip install .
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Usage

### Detect missing entries

Scan specific files:

```bash
find-missing-struct-asym -f path/to/file.cif.gz
```

Scan entire PDB mirror:

```bash
find-missing-struct-asym -m /path/to/pdb/mirror -o results.json
```

### Fix missing entries

Generate corrected CIF files:

```bash
fix-missing-struct-asym -i results.json -o ./fixed/
```

## Corrected Files

Pre-generated corrected files are available in the `fixed/` directory:

- `fixed/1ts6.cif`
- `fixed/2g10.cif`
- `fixed/2k9y.cif`

## Requirements

- Python >= 3.10
- gemmi >= 0.7.0

## License

MIT
