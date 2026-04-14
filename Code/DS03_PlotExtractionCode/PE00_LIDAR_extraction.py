"""LIDAR Extraction.

This script automatically crawls the dataset file structure and looks for the
GOBI and CALIVS LIDAR along with standard plot shapefiles. It then extracts the relevant pixels
from the LIDAR datasets, saving them as a DataFrame.

Notes
-----
The script expects to be run from within a git repository, or with a
``--path`` argument pointing to the dataset root. When run without
``--no-git``, it will resolve the git root and use that as the search
path.

Command-line Arguments
----------------------
--no-git : flag
    Disable git operations.
--path : str, optional
    The path of the folder to look for QA shapefiles. Defaults to the
    root directory of the git repository.
--save-dir : str, optional
    Also save a copy of each extracted spectra file into this
    directory.  The directory is created if it does not exist.
--load-dir : str, optional
    Load previously extracted spectra files from this folder
    (e.g. data received from other nodes) and append them to the
    QC list for plotting.
"""

# ==============================================================================

__title__ = "LIDAR Extraction"
__author__ = "Arden Burrell & Richard Harwood"
__version__ = "v1.0(09.03.2026)"
__email__ = "arden.burrell@sydney.edu.au"


# ==============================================================================

import os
import platform
import getpass
import re
import site
import sys
import git
from git import exc as git_exc
import argparse
import pathlib
from datetime import datetime, date
from typing import Dict, List, Any, Tuple, Optional, Union

# Add git root to Python path before other imports
try:
    git_repo = git.Repo(os.getcwd(), search_parent_directories=True)
    git_root = git_repo.git.rev_parse("--show-toplevel")
    if git_root not in sys.path:
        sys.path.insert(0, git_root)
except git_exc.InvalidGitRepositoryError:
    # If not in a git repo, try to find the root by looking for specific markers
    current_path = pathlib.Path(__file__).resolve()
    for parent in [current_path] + list(current_path.parents):
        if (parent / '.git').exists() or (parent / 'Code').exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            break

import numpy as np
import pandas as pd
import xarray as xr
import rioxarray
import laspy
import geopandas as gpd
# from shapely.geometry import mapping
import yaml
# import json
# from collections import OrderedDict
from tqdm import tqdm
import warnings as warn
from tqdm import tqdm

# Import core functions for parsing the dataset path and extracting metadata
try:
    import Code.functions.core_functions as cf # type: ignore
except ImportError:
    cf = None

# Fix for X11/GUI issues - use non-interactive backend
# import matplotlib
# matplotlib.use('Agg')  # Set backend before importing pyplot
# import matplotlib.pyplot as plt
# import seaborn as sns


# ==================================================================================
def main(args, repo, path):
    # TO DO LIST:
    # 1. Check directory structure and file naming conventions for LIDAR data
    # 2. Find and check the plot shape files
    # 3. Find and check for matching LIDAR datasets (GOBI and CALIVS)
    # 4. Extract the relevant pixels from the LIDAR datasets for each plot and save as a DataFrame
    # OPTIONAL:
    # 5. Make the code able to ignore the folder structure and just look for the files it needs.
    # 6. Add summary stats exist
    
    
    # ========== Make a table of potental folders ==========
    valid_sensors = ["GOBI", "CALVIS"]
    df_flog       = create_field_table(path, valid_sensors, repo, args)
    shapefile_issues: Dict[str, List[str]] = {}

    # ========== Group the table by shapepath then loop through the groups ==========
    for shapepath, group_df in tqdm(df_flog.groupby("shapepath"), desc="Processing project sites"):
        project_name = "unknown_project"
        if "project" in group_df.columns and len(group_df.index) > 0:
            project_name = str(group_df["project"].iloc[0])

        # ========== Check the shape files ==========
        plotshp, valid, issues = load_plot_shapefile(shapepath, args) # type: ignore
        if issues:
            shapefile_issues.setdefault(project_name, [])
            for issue in issues:
                shapefile_issues[project_name].append(f"{shapepath}: {issue}")

        if not valid:#  #FUTURE will make this verbose only
            continue
        # ========== Loop over that table rows ========== 
        lidar_dict_list = []
        # for idx, row in tqdm(group_df.iterrows(), total=group_df.shape[0], desc="Processing runs", leave=False):
        for idx, row in group_df.iterrows():
            lidar_dict_list += find_LIDAR_data(row, plotshp, args) # type: ignore
        
        for lidar_dict in tqdm(lidar_dict_list, desc="Processing LIDAR datasets", total=len(lidar_dict_list), leave=False):
            # ========== Check if it already exsists and if there is a force arg ==========
            lidar_dict = process_LIDAR(lidar_dict, plotshp, args, repo) # type: ignore

            # ========== Add any errors to the issues ==========
            lidar_errors = lidar_dict.get("errors", [])
            if isinstance(lidar_errors, str):
                lidar_errors = [lidar_errors] if lidar_errors else []

            if lidar_errors:
                shapefile_issues.setdefault(project_name, [])
                for issue in lidar_errors:
                    shapefile_issues[project_name].append(f"{lidar_dict['InputLIDAR']}: {issue}")

    # ========== Print a summary of issues ==========
    if shapefile_issues:
        print("\nIssues summary:")
        for project_name in sorted(shapefile_issues.keys()):
            print(f"Project: {project_name}")
            for issue in shapefile_issues[project_name]:
                print(f"  - {issue}")
            
    # breakpoint()
    


# ==================================================================================
# LIDAR specific functions
# ==================================================================================

def process_LIDAR(
        lidar_dict: Dict[str, Any],
        plotshp: gpd.GeoDataFrame,
        args: argparse.Namespace,
        repo: Optional[git.Repo] = None,
    ) -> Dict[str, Any]:
    """Extract LIDAR point cloud data within plot polygons and save as a table.

    Reads the LAS point cloud, clips it to the plot shapefile geometries
    via spatial join, extracts corresponding DTM and DSM elevation values
    at each point location, computes canopy height (Delta_z = z - DTM),
    and writes the result to disk.

    Parameters
    ----------
    lidar_dict : dict
        Metadata dictionary produced by :func:`find_LIDAR_data` with keys:

        - **InputLIDAR** (*pathlib.Path*) -- Path to the .las point cloud.
        - **InputDSM** (*pathlib.Path or None*) -- Path to the DSM raster.
        - **InputDTM** (*pathlib.Path or None*) -- Path to the DTM raster.
        - **outfile** (*pathlib.Path*) -- Output file path.
        - **gpro_nu** (*int*) -- GoPro/acquisition sequence number.

    plotshp : gpd.GeoDataFrame
        Plot layout polygons used to spatially clip the point cloud.
    args : argparse.Namespace
        Parsed command-line arguments. Used for:

        - ``args.savetype`` (*str*) -- Output format (``"csv"`` or ``"parquet"``).
    repo : git.Repo, optional
        Active repository used to enrich metadata with git information.

    Returns
    -------
    dict of str to Any
        The updated ``lidar_dict`` with any errors or metadata appended.

    Warnings
    --------
    Warns if the CRS of the plot shapefile does not match the CRS of the
    LIDAR point cloud or DSM/DTM rasters.

    # TO DO: 
    # Implement some form of metadata saving here
    # Implement some optional chunking

    """
    # ========== Make the metadata file name ==========
    metadata_outfile = lidar_dict["outfile"].with_name(
        f"{lidar_dict['outfile'].stem}_{args.savetype}_metadata.yaml")
    metadata = None

    # ========== Check if the output file already exists and if force is not set ==========
    if lidar_dict["exists"] and not args.force:
        # ========== Load the existing data ==========
        if args.savetype == "csv":
            clipped = pd.read_csv(lidar_dict["outfile"])
        elif args.savetype == "parquet":
            clipped = pd.read_parquet(lidar_dict["outfile"])
        # ========== Load metadata if it exists ==========
        if metadata_outfile.exists():
            with open(metadata_outfile, "r") as f:
                metadata = yaml.safe_load(f)
    else:
        # ========== open the LIDAR dataset ==========
        tqdm.write(f"Processing LIDAR: {lidar_dict['InputLIDAR'].stem} started at {pd.Timestamp.now()}. This may take a while for large rasters, but will be printed to the console when finished.")
        
        pointcloud = laspy.read(lidar_dict["InputLIDAR"])
        crs        = pointcloud.header.parse_crs()
        
        # Extract coordinates and attributes into a DataFrame
        df = pd.DataFrame(pointcloud.xyz, columns=['x', 'y', 'z'])

        # Create GeoDataFrame with Point geometries
        gdf_points = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df.x, df.y),
            crs=crs
        )
        # raise a warning if there is a crs mismatch
        if not plotshp.crs.to_epsg() == crs.to_epsg(): # type: ignore
            warn.warn(f"CRS of plot shapefile ({plotshp.crs.to_epsg()}) does not match CRS of LIDAR point cloud ({crs.to_epsg()}). Performing Conversion")   # type: ignore
            # Ensure plot shapefile CRS matches
            plotshp_proj = plotshp.to_crs(crs) # type: ignore
        else:
            plotshp_proj = plotshp
            
        # Spatial join to clip points within plot polygons
        clipped = gpd.sjoin(
            gdf_points, 
            plotshp_proj, 
            how='inner', 
            predicate='within'
        )
        # +++++ check if clip is empty +++++
        if clipped.empty:
            # add the error to the lidar_dict and return
            lidar_dict["errors"].append(f"No points extracted for {lidar_dict['InputLIDAR']}. Check the plot shapefile and LIDAR data coverage.")
            return lidar_dict
        
        # Convert x and y coordinates to xarray DataArrays
        x_coords = clipped['x'].to_xarray()
        y_coords = clipped['y'].to_xarray()

        # ========== open the DTM and DSM ==========
        clipped = clipped.drop(columns=['geometry'])# Drop geometry column 
        for tif_type in ["DTM", "DSM"]:
            if not lidar_dict[f"Input{tif_type}"] is None:
                # ++++++++++ Check if the crs is matching +++++
                ds = rioxarray.open_rasterio(lidar_dict[f"Input{tif_type}"])

                if not ds.rio.crs.to_epsg() == crs.to_epsg():  # type: ignore
                    lidar_dict["errors"].append(f"CRS matching for {tif_type} rasters not implemented yet. EPGS of raster: {ds.rio.crs.to_epsg()}, EPSG of point cloud: {crs.to_epsg()}. Please check the CRS of your LIDAR data and plot shapefile.")# type: ignore
                    continue

                extracted_values = ds.sel( # type: ignore
                    x=x_coords,
                    y=y_coords,
                    method="nearest"
                )
                # ========== Check if the extracted data is empty ==========
                if extracted_values.size == 0:
                    lidar_dict["errors"].append(f"No valid points extracted for the {tif_type} raster of {lidar_dict['InputLIDAR']}. Check the plot shapefile and LIDAR data coverage.")
                    continue

                npa = np.squeeze(extracted_values.to_numpy())
                clipped[tif_type] = npa
                # +++++ calculate the delta z height +++++
                if tif_type == "DTM":
                    clipped["Delta_z"] = clipped['z'] - npa
        
            # ========= Save the DataFrame to file ==========
            if args.savetype == "csv":
                clipped.to_csv(lidar_dict["outfile"].as_posix(), index=False)
            elif args.savetype == "parquet":
                clipped.to_parquet(lidar_dict["outfile"].as_posix(), index=False)
    
    # ========= Create and save YAML metadata ==========
    if metadata is None:
        # This should work even if the output file already exists, but there is no metadata file, 
        # or if the output file doesn't exist and we just processed the data
        metadata = _metadata(data_dict=lidar_dict, repo=repo)
        metadata_outfile = lidar_dict["outfile"].with_name(
            f"{lidar_dict['outfile'].stem}_{args.savetype}_metadata.yaml"
        )
        with open(metadata_outfile, "w", encoding="utf-8") as f:
            yaml.safe_dump(metadata, f, sort_keys=False)

    # ========= Save the DataFrame to file if there args.savedir is is not none ==========
    # Saves a cop of the data to a central folder for sharing with collaborators or keeping a central record. 
    # The file name is made identifiable by including metadata fields in the name. If the file already exists 
    # and --force is not set, it will skip saving to prevent overwriting.
    if args.save_dir is not None:
        save_path = pathlib.Path(args.save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        # +++++ make an identifiable name for the file based on the metadata +++++
        id_parts: List[str] = []
        for key in ["node", "project", "Site", "sensor", "date", "run", "gpro_nu"]:
            if key not in lidar_dict or lidar_dict[key] is None:
                continue
            val = lidar_dict[key]
            if key == "date":
                try:
                    val = pd.to_datetime(val).strftime("%Y%m%d")
                except Exception:
                    val = str(val)
            sval = str(val).strip().replace("/", "-").replace(" ", "")
            if sval:
                id_parts.append(f"{key}-{sval}")

        identifiable_name = "__".join(id_parts + [lidar_dict["outfile"].stem]) + lidar_dict["outfile"].suffix
        save_file = save_path / identifiable_name
        # +++++ Check if the file already exists and if force is not set +++++
        if not save_file.exists() or args.force:
            if args.savetype == "csv":
                clipped.to_csv(save_file.as_posix(), index=False)
            elif args.savetype == "parquet":
                clipped.to_parquet(save_file.as_posix(), index=False)
        # +++++ Check if the metadata file already exists and if force is not set +++++
        save_metadata_file = save_file.with_name(f"{save_file.stem}_metadata.yaml")
        if not save_metadata_file.exists() or args.force:
            with open(save_metadata_file, "w", encoding="utf-8") as f:
                yaml.safe_dump(metadata, f, sort_keys=False)
    
    # # ========== TO DO: Add some summary stats here ==========
    # breakpoint()
    return lidar_dict


def find_LIDAR_data(
        row: pd.Series,
        plotshp: gpd.GeoDataFrame,
        args: argparse.Namespace,
    ) -> List[Dict[str, Any]]:
    """Find and catalog LIDAR data files for a specific date/sensor/site.

    Searches for LiDAR point cloud files (.las), DSM, and DTM rasters
    associated with the given row's date and sensor information. Creates
    output directory structure and returns metadata dictionaries for
    subsequent processing.

    Parameters
    ----------
    row : pd.Series
        A row from the field log DataFrame containing metadata fields:
        
        - ``datepath`` (*pathlib.Path*) -- Path to the date directory
          where LIDAR data should be located.
        - Other fields for metadata (sensor, date, site, etc.).
    
    plotshp : gpd.GeoDataFrame
        GeoDataFrame containing plot geometries for spatial extraction.
    args : argparse.Namespace
        Parsed command-line arguments. Used for:
        
        - ``args.savetype`` (*str*) -- Output file format (csv/parquet).
    
    Returns
    -------
    list of dict
        List of dictionaries, one per found LIDAR file. Each dict contains:
        
        - **InputLIDAR** (*pathlib.Path*) -- Path to .las point cloud file.
        - **InputDSM** (*pathlib.Path*) -- Path to Digital Surface Model raster.
        - **InputDTM** (*pathlib.Path*) -- Path to Digital Terrain Model raster.
        - **outfile** (*pathlib.Path*) -- Output path for extracted data.
        - **type** (*str*) -- Data type identifier ("LIDAR").
        - **exists** (*bool*) -- Whether output file already exists.
        - **gpro_nu** (*int*) -- GoPro/acquisition sequence number.

    Warnings
    --------
    Warns if multiple or no DSM/DTM files are found for a point cloud.
    It will still genrate the output file path, but the missing or multiple 
    files may cause issues with plot extraction. Please check the LIDAR data files 
    and naming conventions if you see these warnings.
    """
    # ========== Use the information in the row to find the LIDAR data files ==========
    lidar_list = []
    las_list = list(row["datepath"].glob("*/T1_proc/*.gpro/products/*LiDAR_CombinedPointCloud.las"))
    for nu, las in enumerate(las_list):
        errors: List[str] = []
        # +++++ Make the output directory if it doesn't exist +++++
        outpath = las.parents[2] / "Plot_Extraction"
        outpath.mkdir(parents=False, exist_ok=True)
        outfile = outpath / f"LIDAR_Extracted_gp{nu}.{args.savetype}"

        # +++++ Check for DSM and DTM files +++++
        dsm_list = list(las.parents[0].glob("*LiDAR_DSM_*.tif"))
        if len(dsm_list) == 0:
            errors.append(
                f"Missing DSM file for {las}. Expected one file matching '*LiDAR_DSM_*.tif'.")
        elif len(dsm_list) > 1:
            errors.append(
                f"Too many DSM files for {las}. Found {len(dsm_list)} files: {dsm_list}.")

        dtm_list = list(las.parents[0].glob("*LiDAR_DTM_*.tif"))
        if len(dtm_list) == 0:
            errors.append(
                f"Missing DTM file for {las}. Expected one file matching '*LiDAR_DTM_*.tif'.")
        elif len(dtm_list) > 1:
            errors.append(
                f"Too many DTM files for {las}. Found {len(dtm_list)} files: {dtm_list}.")

        # Make a dict with the infomation about the LIDAR file and the output file
        lidar_dict = ({
            "InputLIDAR": las,
            "InputDSM": dsm_list[0] if len(dsm_list) > 0 else None,
            "InputDTM": dtm_list[0] if len(dtm_list) > 0 else None,
            "outpath":outpath,
            "outfile": outfile,
            "type": "LIDAR",
            "exists": outfile.is_file(),
            "gpro_nu": nu,
            "errors": errors,
        })
        # ========== Add additional info to the dict ==========
        for var in row.keys():
            if not var == "Runs": # 
                lidar_dict[var] = row.loc[var]
            else:
                lidar_dict["run"] = int(las.parents[3].name.split('_')[-1])
        
        lidar_list.append(lidar_dict)
    # ========== Return the lidar list ==========
    return lidar_list


# ==================================================================================
# INTERNAL FUNCTIONS THAT MAY BE MOVED TO A SEPARATE MODULE FOR REUSE IN OTHER SCRIPTS
# ==================================================================================

def _to_yaml_compatible(value: Any) -> Any:
    """Convert Python objects into YAML-serializable primitives.

    Parameters
    ----------
    value : Any
        Input object to convert. Supports nested containers and common
        scientific Python objects (for example ``pathlib.Path``,
        ``pandas.Timestamp``, ``numpy`` scalars/arrays, and ``pandas.Series``).

    Returns
    -------
    Any
        YAML-compatible representation of ``value`` where non-serializable
        objects are converted to plain Python primitives.

    Notes
    -----
    Conversion is recursive for dictionaries and sequence-like containers.
    Unsupported objects are converted to ``str`` as a fallback.
    """
    if isinstance(value, pathlib.Path):
        return value.as_posix()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Series):
        return {str(k): _to_yaml_compatible(v) for k, v in value.items()}
    if isinstance(value, dict):
        return {
            str(_to_yaml_compatible(k)): _to_yaml_compatible(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_to_yaml_compatible(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _metadata(
        data_dict: Dict[str, Any],
        repo: Optional[git.Repo] = None,
    ) -> Dict[str, Any]:
    """Build run metadata in YAML-safe form.

    Parameters
    ----------
    data_dict : dict of str to Any
        Metadata dictionary for one processing run.
    repo : git.Repo, optional
        Git repository handle used to append repository metadata. If ``None``,
        git fields are omitted.

    Returns
    -------
    dict of str to Any
        YAML-compatible metadata dictionary containing runtime context,
        system/user information, input metadata, and optional git state.
    """
    metadata = {
        "script_name": pathlib.Path(__file__).name,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "user": getpass.getuser(),
        "system": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
        },
        "data": _to_yaml_compatible(data_dict),
    }

    if repo is not None:
        try:
            active_branch = None
            try:
                active_branch = repo.active_branch.name
            except TypeError:
                active_branch = None
            except Exception:
                active_branch = None

            metadata["git"] = {
                "repo_root": repo.working_tree_dir,
                "commit_hash": repo.head.commit.hexsha,
                "short_hash": repo.git.rev_parse("--short", "HEAD"),
                "branch": active_branch,
                "is_dirty": repo.is_dirty(untracked_files=True),
                "remotes": {
                    remote.name: [url for url in remote.urls]
                    for remote in repo.remotes
                },
            }
        except Exception as exc:
            metadata["git"] = {
                "error": f"Unable to collect git metadata: {exc}"
            }

    return _to_yaml_compatible(metadata)


def load_plot_shapefile(
    shapepath: pathlib.Path,
    args: argparse.Namespace,
    ) -> Tuple[Optional[gpd.GeoDataFrame], bool, List[str]]:
    """Read the experimental plot layout shapefile for a project/site.

    Parameters
    ----------
    shapepath : pathlib.Path
    Path to the directory containing plot layout shapefiles.
    args : argparse.Namespace
    Parsed command-line arguments.

    Returns
    -------
    tuple of (geopandas.GeoDataFrame or None, bool, list of str)
    Tuple containing:
    - The loaded plot layout geometries, or None if no valid shapefile found.
    - Boolean indicating whether a valid shapefile was loaded.
    - List of validation issues collected for deferred reporting.

    Raises
    ------
    FileNotFoundError
    If no shapefile is found in the provided shapepath.
    """
    # ========== Check the path for shapefiles ==========
    shpfiles = list(shapepath.glob("*.shp"))
    # if shapepath.is_dir():
    #     breakpoint()
    valid = True  # Placeholder for actual validation logic
    issues: List[str] = []

    # ========== Check the number of shape files ==========
    if len(shpfiles) == 0:
        issues.append("No shapefile found")
        return None, False, issues

    if len(shpfiles) > 1:
        issues.append(
            f"Found multiple shapefiles, using first: {shpfiles[0]}")

    shp = gpd.read_file(shpfiles[0])

    # ========== Check for expected columns and geometry type ==========
    for columns in ['FID', 'geometry']: # 'Row', 'Range', 
        if not columns in shp.columns:
            issues.append(
                f"Shapefile {shpfiles[0]} missing expected column: {columns}")
            valid = False

    return shp, valid, issues

def create_field_table(path, valid_sensors, repo, args) -> pd.DataFrame:
    """Load field logs for multiple projects and prepare cache directories.

    Parameters
    ----------
    path : pathlib.Path
        Root directory containing project folders.
    repo : git.Repo or None
        The git repository object, or ``None`` if git operations are disabled.
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    pd.DataFrame
        DataFrame containing field log information with shapepaths.
    """
    # ========== workout search procedure for folders ==========
    print("WARNING: Folder search procedure is very much a work in progress. Will be fixed in future updates")
    # parse_APPN_dataset_path

    UseSiteSummary = False  # default behaviour
    parsed_path = None        # parse result when --path is provided; used later for subsetting
    if repo is not None:
        git_root = repo.git.rev_parse("--show-toplevel")
        folder = pathlib.Path(git_root)
        # The git root is always the root level — parse it to confirm and locate NodeSummary.yaml
        if cf is not None:
            parsed = cf.parse_APPN_dataset_path(folder, path_level="root")
            if parsed["valid"] and parsed["root"] is not None:
                root_folder = pathlib.Path(parsed["root"])
                if (root_folder / "NodeSummary.yaml").exists():
                    UseSiteSummary = True
                    folder = root_folder
        else:
            if (folder / "NodeSummary.yaml").exists():
                UseSiteSummary = True

    if args.path is not None:
        folder = pathlib.Path(args.path)
        if cf is not None:
            # Use parse_APPN_dataset_path to find the root from any level in the hierarchy,
            # then check whether NodeSummary.yaml exists there.
            path_level = args.path_level if args.path_level is not None else "auto"
            parsed_path = cf.parse_APPN_dataset_path(folder, path_level=path_level)
            if parsed_path["valid"] and parsed_path["root"] is not None:
                root_folder = pathlib.Path(parsed_path["root"])
                if (root_folder / "NodeSummary.yaml").exists():
                    UseSiteSummary = True
                    folder = root_folder
        else:
            if (folder / "NodeSummary.yaml").exists():
                UseSiteSummary = True
        
    if UseSiteSummary:
        # ========= pathlib recursive glob to look for field logs ==========
        flist = list(folder.rglob("FieldLog.csv"))
        flogs = []

        # ========== Loop over each of the files ========== 
        for summary in flist:
            # +++++ load the csv +++++ 
            dfin    = pd.read_csv(summary)
            
            # +++++ Check for required columns +++++ 
            required_columns = ["Year", "Month", "Day", "Sensor", "Technician", "Runs", "Site", "MakeNotesFile", "CheckSum"]
            missing_columns = [col for col in required_columns if col not in dfin.columns]
            if missing_columns:
                warn.warn(f"CSV file {summary} is missing required columns: {missing_columns}. Expected columns: {required_columns}")
                continue
            
            # +++++ Subset to rows where Sensor is in valid_sensors +++++ 
            dfin = dfin[dfin["Sensor"].isin(valid_sensors)]
            if dfin.empty:
                # project has no relevant data, skip it
                continue
            # +++++ Add project name and date column +++++
            dfin["node"]    = summary.parents[1].name
            dfin["project"] = summary.parents[0].name
            date_components = pd.DataFrame({
                "year": dfin["Year"],
                "month": dfin["Month"],
                "day": dfin["Day"],
            })
            dfin["date"] = pd.to_datetime(date_components)

            # +++++ Make a pathlib path to the project +++++
            pathlist     = []
            datepathlist = []
            for idx, row in dfin.iterrows():
                shapepath = pathlib.Path(folder,row["node"], row["project"], f"{row['Year']}{row['Site']}", "Documentation", "Plot_Layout")
                datepath  = pathlib.Path(folder,row["node"], row["project"], f"{row['Year']}{row['Site']}",row['Sensor'], f"{row['Year']}{row['Month']:02d}{row['Day']:02d}")
                pathlist.append(shapepath)
                datepathlist.append(datepath)

            dfin["shapepath"] = pathlist
            dfin["datepath"]  = datepathlist
                
            flogs.append(dfin)
        # ========== Build a dataframe ==========
        df_flog = pd.concat(flogs, ignore_index=True)

        # ========== If --path was provided, subset to rows matching the parsed level ==========
        if parsed_path is not None and parsed_path["valid"]:
            _level_order = ["root", "node", "project", "site", "sensor", "date"]
            pl = parsed_path["path_level"] if parsed_path["path_level"] in _level_order else "root"
            depth = _level_order.index(pl)
            if depth >= _level_order.index("node") and parsed_path["node"] is not None:
                df_flog = df_flog[df_flog["node"] == parsed_path["node"]]
            if depth >= _level_order.index("project") and parsed_path["project"] is not None:
                df_flog = df_flog[df_flog["project"] == parsed_path["project"]]
            if depth >= _level_order.index("site") and parsed_path["site_folder"] is not None:
                site_col = df_flog["Year"].astype(str) + df_flog["Site"].astype(str)
                df_flog = df_flog[site_col == parsed_path["site_folder"]]
            if depth >= _level_order.index("sensor") and parsed_path["sensor"] is not None:
                df_flog = df_flog[df_flog["Sensor"] == parsed_path["sensor"]]
            if depth >= _level_order.index("date") and parsed_path["date"] is not None:
                df_flog = df_flog[df_flog["date"] == parsed_path["date"]]

    else:
        # No FieldLog.csv found. If cf is available and the path parses as valid,
        # crawl the folder structure directly to discover LIDAR date directories.
        if cf is not None:
            warn.warn("I have never tested this code")
            breakpoint()
            if parsed_path is None:
                # --path was not provided; parse the folder we already have (e.g. git root)
                parsed_path = cf.parse_APPN_dataset_path(folder, path_level="auto")

            if parsed_path is not None and parsed_path["valid"] and parsed_path["root"] is not None:
                flogs = []
                _date_re = re.compile(r"^\d{8}$")
                for date_dir in sorted(folder.rglob("????????")):
                    if not date_dir.is_dir() or not _date_re.match(date_dir.name):
                        continue
                    if date_dir.parent.name not in valid_sensors:
                        continue
                    parsed_date = cf.parse_APPN_dataset_path(date_dir, path_level="date")
                    if (not parsed_date["valid"]
                            or parsed_date["date"] is None
                            or parsed_date["node"] is None
                            or parsed_date["project"] is None
                            or parsed_date["site_folder"] is None):
                        continue
                    dt = parsed_date["date"]
                    root_path = pathlib.Path(parsed_date["root"])
                    flogs.append({
                        "node":          parsed_date["node"],
                        "project":       parsed_date["project"],
                        "Site":          parsed_date["site"],
                        "Year":          parsed_date["year"],
                        "Month":         int(dt.month),
                        "Day":           int(dt.day),
                        "Sensor":        parsed_date["sensor"],
                        "date":          dt,
                        "Runs":          None,
                        "Technician":    None,
                        "MakeNotesFile": None,
                        "CheckSum":      None,
                        "shapepath":     root_path / parsed_date["node"] / parsed_date["project"] / parsed_date["site_folder"] / "Documentation" / "Plot_Layout",
                        "datepath":      date_dir,
                    })

                if flogs:
                    df_flog = pd.DataFrame(flogs)
                else:
                    warn.warn(f"No LIDAR data matching sensors {valid_sensors} found under: {folder}")
                    df_flog = pd.DataFrame(columns=["node", "project", "Site", "Year", "Month", "Day",
                                                     "Sensor", "date", "shapepath", "datepath"])

                # ========== Apply the same path-level subsetting as the FieldLog path ==========
                if parsed_path is not None and parsed_path["valid"] and not df_flog.empty:
                    _level_order = ["root", "node", "project", "site", "sensor", "date"]
                    pl = parsed_path["path_level"] if parsed_path["path_level"] in _level_order else "root"
                    depth = _level_order.index(pl)
                    if depth >= _level_order.index("node") and parsed_path["node"] is not None:
                        df_flog = df_flog[df_flog["node"] == parsed_path["node"]]
                    if depth >= _level_order.index("project") and parsed_path["project"] is not None:
                        df_flog = df_flog[df_flog["project"] == parsed_path["project"]]
                    if depth >= _level_order.index("site") and parsed_path["site_folder"] is not None:
                        site_col = df_flog["Year"].astype(str) + df_flog["Site"].astype(str)
                        df_flog = df_flog[site_col == parsed_path["site_folder"]]
                    if depth >= _level_order.index("sensor") and parsed_path["sensor"] is not None:
                        df_flog = df_flog[df_flog["Sensor"] == parsed_path["sensor"]]
                    if depth >= _level_order.index("date") and parsed_path["date"] is not None:
                        df_flog = df_flog[df_flog["date"] == parsed_path["date"]]

            else:
                warn.warn("Not Implemented yet")
                raise NotImplementedError("The folder search procedure is not implemented yet. This will be fixed in future updates. Please check the folder structure and naming conventions and update the code accordingly.")
        else:
            warn.warn("Not Implemented yet")
            raise NotImplementedError("The folder search procedure is not implemented yet. This will be fixed in future updates. Please check the folder structure and naming conventions and update the code accordingly.")
        breakpoint()
    return df_flog


if __name__ == '__main__':
    # ========== Set the args Description ==========
    description='Optional Command line arguments for script'
    parser = argparse.ArgumentParser(description=description)

    # ========== Add the command line arguments ==========   
    parser = argparse.ArgumentParser(description="Generate dataset folder structure.")
    parser.add_argument("--path", type=str, default=None, help="The path of the folder to look for QA shape files. By default it will search from the root dir of the git repo")
    parser.add_argument("--path-level", type=str, default="site", help="The level in the folder structure that the path provided in --path corresponds to. This is used to correctly extract the metadata from the path. For example, if the path provided is at the 'site' level, then the script will look for the sensor name at the correct level in the path. Default is 'site', but can be set to 'node', 'project',  'site', 'sensor', 'date' or 'run' if the path provided is at a different level.")
    parser.add_argument("-f","--force", default=False, action="store_true", help="Force the creation of files even if one already exists. Default is to skip creating files that already exist to prevent overwriting.")
    parser.add_argument("--savetype", type=str, default="parquet", help="The file type for the output files. Default is csv, but can be set to parquet for more efficient storage and faster read/write times. Note that .parquet files will require additional dependencies to read and write.")
    # parser.add_argument("-s","--skipplot", default=False, action="store_false", help="Generate plots for the extracted spectra. Default is to generate plots. Set this flag to skip plotting if you only want the extracted data tables.")
    # parser.add_argument("--skip-processing", default=False, action="store_true", help="Skip raster processing and only load existing output files for plotting. Useful for faster re-runs when output files already exist.")
    parser.add_argument("--save-dir", type=str, default=None, help="Also save a copy of each extracted spectra file into this directory. Creates the directory if it doesn't exist. Useful for sharing extracted spectra with collaborators or keeping a central record.")
    parser.add_argument("--load-dir", type=str, default=None, help="Load previously extracted spectra files from this folder (e.g. data received from other nodes). Loaded files are appended to the QC list for plotting and can also be copied via --save-dir.")
    parser.add_argument("-v", "--verbose", default=False, action="store_true", help="Enable verbose output for debugging and additional information during processing.")
    args = parser.parse_args()

  # +++++ Check the paths and set exc path to the root of the git folder +++++
    # If --path is provided, use it regardless of git repo status
    if args.path is not None:
        git_root = args.path
        # Try to check if the provided path is within a git repo
        try:
            repo = git.Repo(git_root, search_parent_directories=True)
        except git_exc.InvalidGitRepositoryError:
            repo = None
    else:
        # Otherwise, try to find the git root
        path = os.getcwd()
        try:
            git_repo = git.Repo(path, search_parent_directories=True)
            git_root = git_repo.git.rev_parse("--show-toplevel")
            repo = git.Repo(git_root)
        except git_exc.InvalidGitRepositoryError as err:
            raise git_exc.InvalidGitRepositoryError(
                f"This script was called from an unknown path ({path}). Must be in a git repo or provide a valid --path argument. Original error: {err}"
            ) from err
    
    # ========= Check if the provided path exists ==========
    sys.path.append(git_root)
    os.chdir(git_root)
    path = pathlib.Path(git_root)
    
    if not path.is_dir():
        raise NotADirectoryError(f"The provided path does not exist: {path}")




    # ========== Parse Args to main function ==========
    main(args, repo, path)