"""Tests for parse_APPN_dataset_path.

Tests every explicit path_level using real folder paths across all three storage roots,
plus auto-detection behaviour.  Two tests are marked xfail because they expose a known
bug: when auto mode finds a date node in a *parent* directory (i.e. the input path is
inside a run or T-subfolder), the subsequent ``elif path_level == "date":`` block at the
bottom of the function re-processes the original *input* path (not the detected date
node), overwriting every field with wrong values.

Run with:
    conda activate fire
    cd /mnt/d/APPN-42-datastorage
    pytest Code/DS03_PlotExtractionCode/test_parse_APPN_dataset_path.py -v

Storage roots used (Tier3 2025_Merinda excluded - malformed, no site folder level):
    /mnt/d/APPN-42-datastorage
    /mnt/d/Tier2_DataArchive
    /mnt/d/Tier3_ColdStorage
"""

import pathlib
import sys

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is importable (mirrors what PE00 does at module level)
# ---------------------------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]  # Code/functions/core_functions/tests -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Code.functions.core_functions import parse_APPN_dataset_path  # type: ignore # noqa: E402

# ---------------------------------------------------------------------------
# Storage roots
# ---------------------------------------------------------------------------
APPN  = pathlib.Path("/mnt/d/APPN-42-datastorage")
TIER2 = pathlib.Path("/mnt/d/Tier2_DataArchive")
TIER3 = pathlib.Path("/mnt/d/Tier3_ColdStorage")


def _ts(date_str: str) -> pd.Timestamp:
    """Convenience wrapper so expected dates read cleanly in parametrize."""
    return pd.Timestamp(date_str)


# ===========================================================================
# 1.  Invalid path_level raises ValueError
# ===========================================================================
def test_invalid_path_level_raises():
    with pytest.raises(ValueError, match="Invalid path_level"):
        parse_APPN_dataset_path(APPN / "USYD_Narrabri", path_level="bogus")


# ===========================================================================
# 2.  Root level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root", [APPN, TIER2, TIER3])
def test_root_level_explicit(root):
    result = parse_APPN_dataset_path(root, path_level="root")
    assert result["root"]        == root.as_posix()
    assert result["node"]        is None
    assert result["project"]     is None
    assert result["site_folder"] is None
    assert result["site"]        is None
    assert result["year"]        is None
    assert result["sensor"]      is None
    assert result["date"]        is None
    assert result["run"]         is None
    assert result["path_level"]  == "root"


# ===========================================================================
# 2b. Root level  (auto-detect — no path_level argument)
# ===========================================================================
@pytest.mark.parametrize("root", [APPN, TIER2, TIER3])
def test_root_level_auto(root):
    """Auto-detection resolves the storage roots as path_level='root'."""
    result = parse_APPN_dataset_path(root)
    assert result["path_level"]  == "root"
    assert result["root"]        == root.as_posix()
    assert result["node"]        is None
    assert result["project"]     is None
    assert result["site_folder"] is None
    assert result["site"]        is None
    assert result["year"]        is None
    assert result["sensor"]      is None
    assert result["date"]        is None
    assert result["run"]         is None


# ===========================================================================
# 3.  Node level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root", [APPN, TIER2, TIER3])
def test_node_level_explicit(root):
    path = root / "USYD_Narrabri"
    result = parse_APPN_dataset_path(path, path_level="node")
    assert result["node"]       == "USYD_Narrabri"
    assert result["root"]       == root.as_posix()
    assert result["project"]    is None
    assert result["path_level"] == "node"


# ===========================================================================
# 4.  Project level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root,project", [
    (APPN,  "2025_Chickpea"),
    (APPN,  "2025_ANURhizo"),
    (TIER2, "2025_CSIROCotton"),
    (TIER2, "2025_HeDWICK"),
    (TIER3, "2025_TestData"),
])
def test_project_level_explicit(root, project):
    path = root / "USYD_Narrabri" / project
    result = parse_APPN_dataset_path(path, path_level="project")
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["site_folder"] is None
    assert result["path_level"]  == "project"


# ===========================================================================
# 5.  Site level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,exp_year,exp_site", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      2025, "IAWatson"),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      2025, "Lochearn"),
    (TIER2, "2025_CSIROCotton", "2025Llara",         2025, "Llara"),
    (TIER2, "2025_CSIROCotton", "2024Llara",         2024, "Llara"),
    (TIER2, "2025_HeDWICK",     "2024IAWatson",      2024, "IAWatson"),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", 2024, "HorseArmCreek"),
    (TIER3, "2025_TestData",    "2025CamdenRust",    2025, "CamdenRust"),
])
def test_site_level_explicit(root, project, site_folder, exp_year, exp_site):
    path = root / "USYD_Narrabri" / project / site_folder
    result = parse_APPN_dataset_path(path, path_level="site")
    assert result["site_folder"] == site_folder
    assert result["year"]        == exp_year
    assert result["site"]        == exp_site
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["sensor"]      is None
    assert result["path_level"]  == "site"


# ===========================================================================
# 6.  Sensor level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,sensor", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS"),
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "GOBI"),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      "RHIZO"),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI"),
    (TIER2, "2025_HeDWICK",     "2024IAWatson",      "GOBI"),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", "GOBI"),
])
def test_sensor_level_explicit(root, project, site_folder, sensor):
    path = root / "USYD_Narrabri" / project / site_folder / sensor
    result = parse_APPN_dataset_path(path, path_level="sensor")
    assert result["sensor"]      == sensor
    assert result["site_folder"] == site_folder
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["date"]        is None
    assert result["run"]         is None
    assert result["path_level"]  == "sensor"


# ===========================================================================
# 7.  Date level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,sensor,date_str,exp_date", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS", "20250925", "2025-09-25"),
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS", "20250929", "2025-09-29"),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      "RHIZO",  "20251121", "2025-11-21"),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      "RHIZO",  "20251204", "2025-12-04"),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI",   "20250119", "2025-01-19"),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI",   "20250409", "2025-04-09"),
    (TIER2, "2025_HeDWICK",     "2024IAWatson",      "GOBI",   "20241121", "2024-11-21"),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", "GOBI",   "20241220", "2024-12-20"),
    (TIER3, "2025_TestData",    "2025CamdenRust",    "FIELDOBS", "20250902", "2025-09-02"),
])
def test_date_level_explicit(root, project, site_folder, sensor, date_str, exp_date):
    path = root / "USYD_Narrabri" / project / site_folder / sensor / date_str
    result = parse_APPN_dataset_path(path, path_level="date")
    assert result["date"]        == _ts(exp_date)
    assert result["sensor"]      == sensor
    assert result["site_folder"] == site_folder
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["run"]         is None
    assert result["path_level"]  == "date"


# ===========================================================================
# 8.  Run level  (explicit)
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,sensor,date_str,run_folder,exp_run", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS",   "20250929", "run_00", 0),
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS",   "20250929", "run_01", 1),
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS",   "20250929", "run_02", 2),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      "RHIZO",    "20251121", "run_00", 0),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI",     "20250119", "run_00", 0),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI",     "20250119", "run_01", 1),
    (TIER2, "2025_CSIROCotton", "2025Llara",         "GOBI",     "20250119", "run_02", 2),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", "GOBI",     "20241220", "run_00", 0),
    (TIER3, "2025_TestData",    "2025CamdenRust",    "FIELDOBS", "20250902", "run_00", 0),
])
def test_run_level_explicit(root, project, site_folder, sensor, date_str, run_folder, exp_run):
    path = root / "USYD_Narrabri" / project / site_folder / sensor / date_str / run_folder
    result = parse_APPN_dataset_path(path, path_level="run")
    assert result["run"]         == exp_run
    assert result["run_folder"]  == run_folder
    assert result["date"]        == _ts(date_str)
    assert result["sensor"]      == sensor
    assert result["site_folder"] == site_folder
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["path_level"]  == "run"


# ===========================================================================
# 9.  Auto-detection from an exact date folder  (should pass)
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,sensor,date_str,exp_date", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS",   "20250925", "2025-09-25"),
    (APPN,  "2025_ANURhizo",    "2025Lochearn",      "RHIZO",    "20251204", "2025-12-04"),
    (TIER2, "2025_HeDWICK",     "2024IAWatson",      "GOBI",     "20241121", "2024-11-21"),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", "GOBI",     "20241220", "2024-12-20"),
])
def test_auto_from_date_folder(root, project, site_folder, sensor, date_str, exp_date):
    """Auto correctly resolves when the path IS the date folder."""
    path = root / "USYD_Narrabri" / project / site_folder / sensor / date_str
    result = parse_APPN_dataset_path(path)           # path_level="auto" (default)
    assert result["date"]        == _ts(exp_date)
    assert result["sensor"]      == sensor
    assert result["site_folder"] == site_folder
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()
    assert result["run"]         is None
    assert result["path_level"]  == "date"


# ===========================================================================
# 10.  Auto from a run folder
# ===========================================================================
@pytest.mark.parametrize("root,project,site_folder,sensor,date_str,run_folder,exp_run", [
    (APPN,  "2025_Chickpea",    "2025IAWatson",      "CALVIS", "20250929", "run_01", 1),
    (TIER3, "2025_TestData",    "2024HorseArmCreek", "GOBI",   "20241220", "run_00", 0),
])
def test_auto_from_run_folder(root, project, site_folder, sensor, date_str, run_folder, exp_run):
    """Auto mode from a run-level path should fill all parent fields correctly."""
    path = root / "USYD_Narrabri" / project / site_folder / sensor / date_str / run_folder
    result = parse_APPN_dataset_path(path)
    assert result["run"]         == exp_run
    assert result["run_folder"]  == run_folder
    assert result["date"]        == _ts(date_str)
    assert result["sensor"]      == sensor
    assert result["site_folder"] == site_folder
    assert result["project"]     == project
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == root.as_posix()


# ===========================================================================
# 11.  Auto from a T-subfolder inside a run
# ===========================================================================
@pytest.mark.parametrize("t_folder", ["T0_raw", "T1_proc", "T2_traits"])
def test_auto_from_t_subfolder(t_folder):
    """Auto mode from a T-tier subfolder inside run_00 should still parse correctly."""
    path = (TIER3 / "USYD_Narrabri" / "2025_TestData"
            / "2024HorseArmCreek" / "GOBI" / "20241220" / "run_00" / t_folder)
    result = parse_APPN_dataset_path(path)
    assert result["date"]        == _ts("2024-12-20")
    assert result["sensor"]      == "GOBI"
    assert result["site_folder"] == "2024HorseArmCreek"
    assert result["project"]     == "2025_TestData"
    assert result["node"]        == "USYD_Narrabri"
    assert result["root"]        == TIER3.as_posix()
    assert result["run_folder"]  == "run_00"
    assert result["run"]         == 0


# ===========================================================================
# 12.  Validation — bad field names produce valid=False with error messages
# ===========================================================================

# Fake base that doesn't need to exist on disk (no filesystem checks at these levels)
_FAKE = pathlib.Path("/mnt/z/FakeRoot/USYD_Narrabri")
_FAKE_DATE = _FAKE / "2025_Chickpea" / "2025IAWatson" / "CALVIS" / "20250929"


def test_bad_project_name():
    """A project folder not matching YYYY_Name → valid=False."""
    result = parse_APPN_dataset_path(_FAKE / "NotAProject", path_level="project")
    assert result["valid"]  is False
    assert any("NotAProject" in e for e in result["errors"])
    # All data fields cleared
    assert result["project"] is None
    assert result["node"]    is None


def test_bad_run_folder():
    """A run folder with a hyphen (run-00) doesn't match run_regex → valid=False."""
    result = parse_APPN_dataset_path(_FAKE_DATE / "run-00", path_level="run")
    assert result["valid"]       is False
    assert any("run-00" in e for e in result["errors"])
    assert result["run_folder"]  is None
    assert result["run"]         is None


def test_bad_tier_name():
    """A tier folder not starting with T<digit>_ → valid=False."""
    result = parse_APPN_dataset_path(_FAKE_DATE / "run_00" / "raw_data", path_level="tier")
    assert result["valid"]  is False
    assert any("raw_data" in e for e in result["errors"])
    assert result["tier"]   is None


def test_bad_date_folder():
    """A date folder with an invalid calendar date (month 13) → NaT → valid=False."""
    bad_date_path = _FAKE / "2025_Chickpea" / "2025IAWatson" / "CALVIS" / "20251399"
    result = parse_APPN_dataset_path(bad_date_path, path_level="date")
    assert result["valid"]  is False
    assert any("valid date" in e for e in result["errors"])
    assert result["date"]   is None


# ===========================================================================
# 13.  Paths deeper than sub_tier — stem is captured
# ===========================================================================

# Constructed deep path: .../run_00/T0_raw/plotdata/field_data
_DEEP_AUTO = (pathlib.Path("/mnt/z/FakeRoot/USYD_Narrabri")
              / "2025_Chickpea" / "2025IAWatson" / "CALVIS"
              / "20250929" / "run_00" / "T0_raw" / "plotdata" / "field_data")


def test_auto_path_deeper_than_sub_tier():
    """Auto mode: parts below sub_tier are joined into 'stem'."""
    result = parse_APPN_dataset_path(_DEEP_AUTO)
    assert result["valid"]       is True
    assert result["run_folder"]  == "run_00"
    assert result["run"]         == 0
    assert result["tier"]        == "T0_raw"
    assert result["sub_tier"]    == "plotdata"
    assert result["stem"]        == "field_data"
    assert result["date"]        == _ts("2025-09-29")
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"


def test_explicit_sub_tier_path_deeper_than_sub_tier():
    """Explicit path_level='sub_tier': anchor is found correctly and stem is set."""
    result = parse_APPN_dataset_path(_DEEP_AUTO, path_level="sub_tier")
    assert result["valid"]       is True
    assert result["sub_tier"]    == "plotdata"
    assert result["stem"]        == "field_data"
    assert result["tier"]        == "T0_raw"
    assert result["run_folder"]  == "run_00"
    assert result["run"]         == 0
    assert result["date"]        == _ts("2025-09-29")
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"


def test_explicit_sub_tier_multiple_levels_deep():
    """Explicit path_level='sub_tier' with 3 extra levels below sub_tier → stem captures all."""
    deep3 = _DEEP_AUTO / "extra" / "deep"
    result = parse_APPN_dataset_path(deep3, path_level="sub_tier")
    assert result["valid"]      is True
    assert result["sub_tier"]   == "plotdata"
    assert result["stem"]       == "field_data/extra/deep"
    assert result["tier"]       == "T0_raw"
    assert result["run_folder"] == "run_00"


# ===========================================================================
# 14.  ISO date format  (YYYY-MM-DD)
# ===========================================================================

_FAKE_ISO = _FAKE / "2025_Chickpea" / "2025IAWatson" / "CALVIS"


@pytest.mark.parametrize("date_str,exp_date", [
    ("2025-09-25", "2025-09-25"),
    ("2025-09-29", "2025-09-29"),
    ("2024-11-21", "2024-11-21"),
    ("2024-12-20", "2024-12-20"),
])
def test_date_level_explicit_iso(date_str, exp_date):
    """Date folders in YYYY-MM-DD format are parsed to the correct Timestamp."""
    result = parse_APPN_dataset_path(_FAKE_ISO / date_str, path_level="date")
    assert result["valid"]       is True
    assert result["date"]        == _ts(exp_date)
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"
    assert result["run"]         is None
    assert result["path_level"]  == "date"


@pytest.mark.parametrize("date_str,run_folder,exp_run", [
    ("2025-09-29", "run_00", 0),
    ("2025-09-29", "run_01", 1),
    ("2024-12-20", "run_00", 0),
])
def test_run_level_explicit_iso(date_str, run_folder, exp_run):
    """Run folders under YYYY-MM-DD date folders are parsed correctly."""
    result = parse_APPN_dataset_path(_FAKE_ISO / date_str / run_folder, path_level="run")
    assert result["valid"]       is True
    assert result["run"]         == exp_run
    assert result["run_folder"]  == run_folder
    assert result["date"]        == _ts(date_str)
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"
    assert result["path_level"]  == "run"


@pytest.mark.parametrize("date_str,exp_date", [
    ("2025-09-25", "2025-09-25"),
    ("2024-11-21", "2024-11-21"),
])
def test_auto_from_iso_date_folder(date_str, exp_date):
    """Auto mode detects YYYY-MM-DD as the date level."""
    result = parse_APPN_dataset_path(_FAKE_ISO / date_str)
    assert result["valid"]       is True
    assert result["date"]        == _ts(exp_date)
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"
    assert result["run"]         is None
    assert result["path_level"]  == "date"


@pytest.mark.parametrize("date_str,run_folder,exp_run", [
    ("2025-09-29", "run_01", 1),
    ("2024-12-20", "run_00", 0),
])
def test_auto_from_run_under_iso_date(date_str, run_folder, exp_run):
    """Auto mode from a run folder under a YYYY-MM-DD date folder."""
    result = parse_APPN_dataset_path(_FAKE_ISO / date_str / run_folder)
    assert result["valid"]       is True
    assert result["run"]         == exp_run
    assert result["run_folder"]  == run_folder
    assert result["date"]        == _ts(date_str)
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"


@pytest.mark.parametrize("t_folder", ["T0_raw", "T1_proc", "T2_traits"])
def test_auto_from_t_subfolder_iso_date(t_folder):
    """Auto mode from a T-tier subfolder under a YYYY-MM-DD date folder."""
    path = _FAKE_ISO / "2025-09-29" / "run_00" / t_folder
    result = parse_APPN_dataset_path(path)
    assert result["valid"]       is True
    assert result["date"]        == _ts("2025-09-29")
    assert result["tier"]        == t_folder
    assert result["run_folder"]  == "run_00"
    assert result["run"]         == 0
    assert result["sensor"]      == "CALVIS"
    assert result["site_folder"] == "2025IAWatson"
    assert result["project"]     == "2025_Chickpea"
    assert result["node"]        == "USYD_Narrabri"


def test_bad_iso_date_folder():
    """An ISO date folder with an invalid calendar date (month 13) → NaT → valid=False."""
    result = parse_APPN_dataset_path(_FAKE_ISO / "2025-13-99", path_level="date")
    assert result["valid"]  is False
    assert any("valid date" in e for e in result["errors"])
    assert result["date"]   is None


def test_iso_and_compact_date_same_timestamp():
    """YYYY-MM-DD and YYYYMMDD for the same date produce identical Timestamps."""
    compact = parse_APPN_dataset_path(_FAKE_ISO / "20250929", path_level="date")
    iso     = parse_APPN_dataset_path(_FAKE_ISO / "2025-09-29", path_level="date")
    assert compact["date"] == iso["date"]


# ===========================================================================
# 15.  Hierarchy alignment diagnostics
#
# These tests cover the structural error messages emitted when one of the
# expected layers (sensor / site / project / node) is missing or an
# unexpected layer has been inserted into the path. The motivating real
# example was Tier3 ``USYD_Narrabri/2025_Merinda/GOBI/...`` which has no
# site folder between project and sensor.
# ===========================================================================

# Canonical good base used to build malformed variants.
_VALID_SUB_TIER = (
    pathlib.Path("/mnt/z/FakeRoot")
    / "USYD_Narrabri" / "2025_Chickpea" / "2025IAWatson" / "CALVIS"
    / "20250929" / "run_00" / "T0_raw" / "X.gpro"
)


def test_alignment_valid_baseline():
    """Sanity check that the canonical fake path validates cleanly."""
    result = parse_APPN_dataset_path(_VALID_SUB_TIER, path_level="sub_tier")
    assert result["valid"] is True
    assert result["errors"] == []


def test_alignment_missing_site_folder():
    """Site folder omitted between project and sensor (Merinda real case)."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Merinda" / "GOBI"
           / "20250227" / "run_06" / "T1_proc" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    msg = " ".join(result["errors"])
    assert "missing a site folder" in msg
    assert "GOBI" in msg
    assert "2025_Merinda" in msg


def test_alignment_missing_project_folder():
    """Project folder omitted between node and site."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025IAWatson" / "CALVIS"
           / "20250929" / "run_00" / "T0_raw" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    msg = " ".join(result["errors"])
    assert "missing a project folder" in msg
    assert "2025IAWatson" in msg
    assert "USYD_Narrabri" in msg


def test_alignment_missing_sensor_folder():
    """Sensor folder omitted between site and date."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Chickpea" / "2025IAWatson"
           / "20250929" / "run_00" / "T0_raw" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    msg = " ".join(result["errors"])
    assert "missing a sensor folder" in msg


def test_alignment_extra_layer_between_project_and_site():
    """An unexpected folder spliced in between project and site."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Chickpea" / "EXTRA"
           / "2025IAWatson" / "CALVIS"
           / "20250929" / "run_00" / "T0_raw" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    msg = " ".join(result["errors"])
    assert "unexpected extra folder" in msg
    assert "EXTRA" in msg


def test_alignment_extra_layer_between_site_and_sensor():
    """An unexpected folder spliced in between site and sensor."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Chickpea" / "2025IAWatson"
           / "JUNK" / "CALVIS"
           / "20250929" / "run_00" / "T0_raw" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    msg = " ".join(result["errors"])
    assert "unexpected extra folder" in msg
    assert "JUNK" in msg


def test_alignment_error_mentions_expected_layout():
    """All structural error messages should include the expected layout hint."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Merinda" / "GOBI"
           / "20250227" / "run_06" / "T1_proc" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    assert any("<node>/<project>/<site>/<sensor>/<date>" in e
               for e in result["errors"])


def test_alignment_clears_fields_on_failure():
    """When validation fails, parsed metadata fields are cleared to None."""
    bad = (pathlib.Path("/mnt/z/FakeRoot")
           / "USYD_Narrabri" / "2025_Merinda" / "GOBI"
           / "20250227" / "run_06" / "T1_proc" / "X.gpro")
    result = parse_APPN_dataset_path(bad, path_level="sub_tier")
    assert result["valid"] is False
    for key in ("node", "project", "site_folder", "sensor",
                "date", "run_folder", "run", "tier", "sub_tier"):
        assert result[key] is None, f"expected {key!r} to be cleared, got {result[key]!r}"

