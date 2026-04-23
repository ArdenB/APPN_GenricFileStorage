# LIDAR Plot Extraction

## Overview

This script automates the extraction of plot-level LIDAR point cloud data from hyperspectral imaging campaigns. It crawls the APPN dataset file structure to locate GOBI and CALVIS LIDAR point clouds along with their matching DSM/DTM rasters and plot-layout shapefiles, clips the point cloud to each plot polygon, attaches DTM/DSM elevations at each point, computes canopy height (`Delta_z = z - DTM`), and writes the result to disk. It is designed to run inside a directory that follows the APPN folder structure.

**Version:** v1.0 (09.03.2026)
**Authors:** Arden Burrell & Richard Harwood

## What It Does

1. **Discovers** `FieldLog.csv` files under the dataset root (or crawls the folder hierarchy directly when no field logs are present)
2. **Filters** rows to GOBI and CALVIS LIDAR acquisitions
3. **Loads and validates** plot-layout shapefiles under `Documentation/Plot_Layout/`
4. **Locates** matching LIDAR files for each date directory:
   - `*LiDAR_CombinedPointCloud.las` (point cloud)
   - `*LiDAR_DSM_*.tif` (digital surface model)
   - `*LiDAR_DTM_*.tif` (digital terrain model)
5. **Clips** each point cloud to the plot polygons via spatial join
6. **Extracts** DSM/DTM values at each point and computes `Delta_z` (canopy height)
7. **Writes** extracted tables to a `Plot_Extraction/` folder alongside the source data (`.csv` or `.parquet`)
8. **Writes** a YAML metadata sidecar capturing runtime, system, user, and git state
9. **Supports** sharing across nodes via `--save-dir` / `--load-dir`

## Prerequisites

### Required Python Packages

```bash
- numpy
- pandas
- xarray
- rioxarray
- laspy
- geopandas
- shapely
- pyyaml
- tqdm
- GitPython
```

### Setting Up a Conda Environment

```bash
conda create -n lidar-extract python=3.13 -c conda-forge
conda activate lidar-extract

conda install -c conda-forge \
    numpy pandas xarray rioxarray laspy \
    geopandas shapely pyyaml tqdm gitpython
```

### System Requirements

- Python 3.12+ (3.13 recommended)
- Must be run from within an APPN folder-structure git repository, or with the `--path` argument pointing to one
- Dataset must follow the APPN folder structure (see below)

## Command-Line Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--path` | str | (git root) | Root path to search. Defaults to the git repository root. |
| `--path-level` | str | `site` | Level in the folder hierarchy that `--path` corresponds to. One of `root`, `node`, `project`, `site`, `sensor`, `date`, `run`. Used to subset the field-log table to the requested scope. |
| `-f`, `--force` | flag | False | Force re-creation of output files, overwriting existing ones. |
| `--savetype` | str | `parquet` | Output file format: `csv` or `parquet`. Parquet is more efficient but requires additional dependencies. |
| `--save-dir` | str | None | Also save a copy of each extracted file (and its metadata sidecar) into this directory for sharing/archiving. |
| `--load-dir` | str | None | Load previously extracted files from this directory (e.g. received from other nodes). |
| `-v`, `--verbose` | flag | False | Enable detailed output for debugging. |

## Usage Examples

### Basic Usage

Run from within the git repository:

```bash
python PE00_LIDAR_extraction.py
```

### Specify a Custom Path

```bash
python PE00_LIDAR_extraction.py --path /path/to/APPNfolderstructure --path-level root
```

### Process a Single Site

```bash
python PE00_LIDAR_extraction.py --path /path/to/node/project/2026SiteA --path-level site
```

### Force Regeneration

```bash
python PE00_LIDAR_extraction.py --force
```

### Use CSV Output

```bash
python PE00_LIDAR_extraction.py --savetype csv
```

### Share Extractions Between Nodes

```bash
# Save identifiable copies for sharing
python PE00_LIDAR_extraction.py --save-dir /path/to/shared/lidar
```

The copy is renamed using metadata fields (node, project, site, sensor, date, run, gpro_nu) so files from different nodes don't collide when combined.

## Expected Folder Structure

```
workspace_root/
├── NodeSummary.yaml
└── node_name/
    └── project_name/
        ├── FieldLog.csv                              # drives the scan
        └── YYYYSiteName/
            ├── Documentation/
            │   └── Plot_Layout/
            │       └── *.shp                         # plot polygons
            └── {GOBI|CALVIS}/
                └── YYYYMMDD/
                    └── run_XX/
                        └── T1_proc/
                            ├── Plot_Extraction/      # created by script
                            └── *.gpro/
                                └── products/
                                    ├── *LiDAR_CombinedPointCloud.las
                                    ├── *LiDAR_DSM_*.tif
                                    └── *LiDAR_DTM_*.tif
```

### Required Inputs

- **`FieldLog.csv`** at the project level, with columns: `Year`, `Month`, `Day`, `Sensor`, `Technician`, `Runs`, `Site`, `MakeNotesFile`, `CheckSum`.
- **Plot shapefile** with a `FID` column and `geometry` column (polygons).
- **LiDAR point cloud** named `*LiDAR_CombinedPointCloud.las` under `*.gpro/products/`.
- **DSM and DTM rasters** named `*LiDAR_DSM_*.tif` and `*LiDAR_DTM_*.tif` in the same `products/` folder.

## Output Files

### Extracted Tables

Written to `T1_proc/Plot_Extraction/` alongside each LIDAR acquisition:

```
LIDAR_Extracted_gp{N}.{csv|parquet}
LIDAR_Extracted_gp{N}_{savetype}_metadata.yaml
```

**Columns:**

- `x`, `y`, `z` — point cloud coordinates
- `DTM`, `DSM` — raster values at each point (nearest neighbour)
- `Delta_z` — canopy height (`z - DTM`)
- Plot shapefile attributes joined via spatial `within` predicate (e.g. `FID`)

### Metadata Sidecar

A YAML file recording:

- Script name, UTC generation time, user, hostname, platform, Python version and executable
- The full `lidar_dict` for the run (input paths, output path, sensor, date, run, etc.)
- Git state: repo root, commit hash, short hash, branch, dirty flag, remotes

### Shared Copies (`--save-dir`)

If `--save-dir` is provided, extracted files are also copied there with a self-describing name:

```
node-<node>__project-<project>__Site-<site>__sensor-<sensor>__date-YYYYMMDD__run-<run>__gpro_nu-<n>__LIDAR_Extracted_gp<n>.<ext>
```

Existing files in the shared directory are not overwritten unless `--force` is set.

## Supported Sensors

- **GOBI** — LIDAR + VNIR
- **CALVIS** — LIDAR + VNIR + SWIR

Only `GOBI` and `CALVIS` rows in `FieldLog.csv` are processed.

## Workflow

1. **Resolve root:** determine git root (or use `--path`), then locate `NodeSummary.yaml` at the dataset root.
2. **Build field table:** glob all `FieldLog.csv` files, validate required columns, filter to valid sensors, annotate with derived `shapepath` and `datepath`. Optionally subset by `--path-level`.
3. **Per project-site:** load and validate the plot shapefile (checks for `FID` and `geometry`).
4. **Per run:** glob for LIDAR point cloud, DSM, and DTM files; create output directory.
5. **Process:** read the `.las`, spatial-join to plot polygons, extract DSM/DTM nearest-neighbour values, compute `Delta_z`, write `csv`/`parquet`.
6. **Metadata:** write a YAML sidecar with runtime and git context.
7. **Share:** copy to `--save-dir` if provided.
8. **Report:** print a per-project summary of any validation or processing issues.

## Troubleshooting

### Common Issues

**"CSV file ... is missing required columns"**
- Open the offending `FieldLog.csv` and ensure the nine required columns exist with the exact names.

**"No shapefile found" / "missing expected column: FID"**
- Verify `Documentation/Plot_Layout/*.shp` exists and contains `FID` and `geometry`.

**"Missing DSM file" / "Missing DTM file"**
- Check the `.gpro/products/` folder for files matching `*LiDAR_DSM_*.tif` and `*LiDAR_DTM_*.tif`.

**"Too many DSM/DTM files"**
- The script expects exactly one DSM and one DTM per point cloud. Remove or move extras.

**"CRS of plot shapefile does not match CRS of LIDAR point cloud"**
- This is a warning — the plot shapefile is reprojected to the point cloud CRS automatically.
- If raster CRS mismatches the point cloud, the script errors out for that raster (CRS conversion for rasters is not yet implemented).

**"No points extracted"**
- The point cloud and plot polygons don't overlap (wrong CRS, wrong site, empty plot layout).

### Verbose Mode

```bash
python PE00_LIDAR_extraction.py --verbose
```

## Notes

- Processing large point clouds may take several minutes per file.
- Parquet output is recommended for large plots (faster I/O, smaller files).
- The folder-search fallback (used when no `FieldLog.csv` is found) is flagged as experimental and includes a `breakpoint()` — use field logs where possible.
- A final `breakpoint()` call in `main()` is currently commented out; re-enable it for interactive inspection if needed.

## Future Enhancements

Planned features (see TODOs in code):

- Summary statistics per plot
- CRS conversion for DSM/DTM rasters
- Optional chunked processing of very large point clouds
- Broader support for running without `FieldLog.csv`

## Contact

For questions or issues, contact: arden.burrell@sydney.edu.au
