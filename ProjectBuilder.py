"""
Py script to automatically generate a folder structure
"""

# ==============================================================================

__title__ = "Dataset File Structure"
__author__ = "Arden Burrell"
__version__ = "v1.0(22.05.2025)"
__email__ = "arden.burrell@sydney.edu.au"


# ==============================================================================

import os
import sys
import git
import argparse
import pathlib

# ==============================================================================
# ========== Import packages ==========
import numpy as np
import pandas as pd
import yaml
# import ipdb

# ==============================================================================

def main(args, repo):

    # ========== pull the repo ==========
    if not args.no_git:
        GitPull(repo)
    # ========== set Flag to determine if the git repo has been modified ==========
    gitmod = False

    # ========== make and check the node folders ==========
    # +++++ Load the node yaml file +++++
    nodeinfo = yaml.safe_load(open(f"{args.projectsYAML}", "r"))
    # +++++ Loop over each node +++++
    for node in nodeinfo["nodes"]:
        # +++++ Check the folders and the project log +++++
        df, gitmod  = NodeChecker(args, node, gitmod)

        # ========== Make the column names for the csv file ==========
        colnames = ["Year", "Month", "Day", "Sensor", "Technician", "Runs", "Site", "MakeNotesFile", "CheckSum"]

        # ========== Check if there are any project ==========
        if df.empty:
            break # Exit the loop as ther are no projects to make files for
        
        # ========== Loop over every project ==========
        for project, row in df.iterrows():

            # ========== Check the project info and make folders ==========
            df_flog, gitmod, flog_fname, Site_names, ProjectInfo, = projBuilder(project, node, colnames, args, repo, gitmod)

            # ========== Check Has any valid field entries ==========
            if not  df_flog.empty:
                # +++++ Loop over each experimental day +++++
                for index, frow in df_flog.iterrows():
                    # +++++ Sanity check the row +++++
                    check, site = Rowchecker(flog_fname, frow, row, ProjectInfo, args.historical)

					# +++++ Make the site name +++++
                    df_flog, gitmod =  Sitebuilder(flog_fname, df_flog, index, frow, check, site, project, node, args, repo, gitmod)


    # ========== Do a git commit ==========
    if gitmod:
        if not args.no_git:
            print(f"Code Sucessfull. New files and folders created. Starting git push at {pd.Timestamp.now()}")
            repo.index.commit(f'Commit from python script {__file__}. ')
            repo.git.push()
        else:
            print(f"Code Sucessfull. Git Disabled with command line arguments")
        # breakpoint()
    else:
        print("Code Sucessfull. No new files created")
    
    # breakpoint()

#==============================================================================
def Sitebuilder(flog_fname, df_flog, index, frow, check, site, project, node, args, repo, gitmod):
    """
    Create and organize the folder structure for a site, including sensor and run folders.

    Parameters
    ----------
	flog_fname : str
		Path to the field log CSV file.
    df_flog : pandas.DataFrame
		DataFrame containing the field log information.
    index : int
		Index of the row in the field log DataFrame to update.
    frow : pandas.Series
        Row from the field log DataFrame containing field day information.
    check : float or None
        Checksum value to update in the field log, or None if not needed.
    site : dict
        Dictionary containing site information.
    project : str
        Name of the project.
    node : dict
        Dictionary containing node information.
    args : argparse.Namespace
        Parsed command-line arguments.
    repo : git.Repo
        GitPython Repo object for git operations.
    gitmod : bool
        Flag indicating if the git repo has been modified.

    Returns
    -------
    df_flog : pandas.DataFrame
		Updated field log DataFrame with the checksum.
    gitmod : bool
        Updated git modification flag.

    Notes
    -----
    - Creates sensor and run folders for the site.
    - Optionally creates a FieldNotes.txt file.
    - Updates the field log and adds it to git if required.
    """
    # ========== Make the site name ==========
    sitename = _sitenamemaker(site)
    
	# +++++ Check if there is already a sensor folder +++++
    pymkdir(f"./{node["name"]}/{project}/{sitename}/{frow.Sensor}")
    # TO DO: Ammend the ProjectInfo to include the sensor
    # TO DO: Add the sensor to the project yaml file
    
	# +++++ Make the field day folder +++++
    dname    = f"{frow.Year:02d}{frow.Month:02d}{frow.Day:02d}"
    folder  = f"./{node["name"]}/{project}/{sitename}/{frow.Sensor}/{dname}"
    for runNo in np.arange(frow.Runs):
        for fldr in ["T0_raw", "T1_proc", "T2_traits"]:
            pymkdir(f"{folder}/run_{runNo:02d}/{fldr}")

        sensors_QC = ["GOBI", "CALVIS"] # Add more sensors with QC data here
        if frow.Sensor in sensors_QC:
            pymkdir(f"{folder}/run_{runNo:02d}/T1_proc/QC_data")
    
	# +++++ Make a log file +++++
    if frow.MakeNotesFile == True:
        pathlib.Path(f"{folder}/FieldNotes.txt").touch()
    
    # ========== Add the Check Sum and add the file to git ==========
    if not check is None:
        df_flog.loc[index,"CheckSum"] = check
        df_flog.to_csv(flog_fname, index=False)
        # +++++ Add the file to the github repo +++++ 
        if not args.no_git:
            repo.git.add(flog_fname)
            gitmod = True
    return df_flog, gitmod

def projBuilder(project, node, colnames, args, repo, gitmod):
    """
    Load project info and ensure required folders and files exist.

    Parameters
    ----------
    project : str
        The project name.
    node : dict
        Dictionary containing node information (e.g., name).
    colnames : list of str
        List of column names for the field log CSV.
    args : argparse.Namespace
        Parsed command-line arguments.
    repo : git.Repo
        GitPython Repo object for git operations.
    gitmod : bool
        Flag indicating if the git repo has been modified.

    Returns
    -------
    df_flog : pandas.DataFrame
        The loaded or newly created field log DataFrame.
    gitmod : bool
        Updated git modification flag.
    flog_fname : str
        Path to the field log CSV file.
    Site_names : list of str
        List of standardized site names.
    ProjectInfo : dict
        Loaded project YAML data.

    Notes
    -----
    - Creates 'Documentation' and 'Code' folders if missing.
    - Creates a project YAML summary if missing.
    - Creates a field log CSV if missing.
    - Adds new files to git if enabled.
    """
    # ========== Check the folders exist ==========
    for fld in ["Documentation", "Code"]:
        pymkdir(f"./{node["name"]}/{project}/{fld}")
    
    # ========== Load a project yaml ==========
    psyl_fname = f"./{node["name"]}/{project}/ProjectSummary.yaml"
    ProjectInfo, gitmod = _projYAML(project, psyl_fname, args, repo, gitmod)
    

    # ========== Check the field log ==========
    flog_fname = f"./{node["name"]}/{project}/FieldLog.csv"
    if not os.path.isfile(flog_fname):
        # +++++ Create and empty field log +++++
        df_flogO = pd.DataFrame(columns=colnames)
        df_flogO.to_csv(flog_fname, index=False)

        # ========== Add the file to the github repo ========== 
        if not args.no_git:
            repo.git.add(flog_fname)
            gitmod = True
    
        # +++++ Open the log files +++++
        df_flog = pd.read_csv(flog_fname)
    else:
        # +++++ Load the field log file +++++
        df_flog = pd.read_csv(flog_fname)
        # +++++ Sanity check the file +++++
        df_flog, gitmod = _df_col_check(df_flog, flog_fname, colnames, args, repo, gitmod)

    # ========== Make sure folders exist of all of the sites ==========
    Site_names = []
    for site in ProjectInfo["project"]["sites"]:
        if not site["name"] == "" and not site["year"] == -9999:
            # ========== To Do Sanity check a log file ==========
            # This will also need to include some ability to edit files
            # breakpoint()
            sitename = _sitenamemaker(site, psyl_fname)
            Site_names.append(sitename)
            
            # +++++ Check if the site folder exists +++++
            pymkdir(f"./{node["name"]}/{project}/{sitename}")
            for fld in ["Documentation", "Code"]:
                pymkdir(f"./{node["name"]}/{project}/{sitename}/{fld}")

    return df_flog, gitmod, flog_fname, Site_names, ProjectInfo, 


def NodeChecker(args, node, gitmod):
    """
    Ensure node folder and project summary CSV exist, and check for missing columns.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed command-line arguments.
    node : dict
        Dictionary containing node information (e.g., name, SensorPlatforms).
    gitmod : bool
        Flag indicating if the git repo has been modified.

    Returns
    -------
    df : pandas.DataFrame
        DataFrame of the node's project summary.
    gitmod : bool
        Updated git modification flag.

    Notes
    -----
    - Creates the node folder and project summary CSV if missing.
    - Adds new files to git if enabled.
    - Ensures all required columns are present in the CSV.
    """
    # +++++ Check if the folder exist already +++++
    pymkdir(f"./{node["name"]}")

    # +++++ Check if project csv already exists +++++
    # This file is a bool array of projects vs sensors
    pfilename = f"./{node["name"]}/{node["name"]}_ProjectsSummary.csv"

    # ========= Check if the file already exists and has the correct columns =========
    if not os.path.isfile(pfilename):
        # +++++ Create and empty field log +++++
        df_proj = pd.DataFrame(columns=["Project"]+node["SensorPlatforms"])
        df_proj.to_csv(pfilename, index=False)
        print(f"New Node Project Summary table built:{pfilename}")


        # ========== Add the file to the github repo ========== 
        if not args.no_git:
            repo.git.add(pfilename)
            gitmod = True

    # ========== Load the file with projects and fix any missing columns ==========
    # Always read in the csv for consistency check to avoid read issues
    df = pd.read_csv(pfilename, header=0, index_col=0)
    df, gitmod = _df_col_check(df, pfilename, node["SensorPlatforms"], args, repo, gitmod, fill_val=False)

    # +++++ Check if the file has been changed git status +++++
    if not args.no_git:
        gitmod = GitChanged(repo, pfilename, gitmod)

    return df, gitmod


def _projYAML(project, pym_fn, args, repo, gitmod):
    """
    Ensure a project YAML file exists and is loaded.

    Parameters
    ----------
    project : str
        The project name.
    pym_fn : str
        Path to the project YAML file.
    args : argparse.Namespace
        Parsed command-line arguments.
    repo : git.Repo
        GitPython Repo object for git operations.
    gitmod : bool
        Flag indicating if the git repo has been modified.

    Returns
    -------
    Proj_data : dict
        Loaded project YAML data.
    gitmod : bool
        Updated git modification flag.

    Notes
    -----
    - Creates a template YAML file if missing.
    - Adds new files to git if enabled.
    """
    # +++++ Check if the project yaml file already exists +++++
    if not os.path.isfile(pym_fn):
        project_data = {
            "project": {
                "ShortName": f"{project}",
                "FullName": "",
                "description": "",
                "start_date": "",
                "end_date": "",
                "funding_source": "",
                "status": "",
                "ProjectCode":"",
                "Internal":None,
                "researcher": {
                    "FirstName": "",
                    "LastName":"",
                    "Title":"",
                    "email": "",
                    "institution": "",
                    "role": "Principal Investigator",
                    "orcid": ""
                },
                "sites": [
                    {
                        "name": "",
                        "year": -9999,# This is a placeholder for the year
                        "season": "",
                        "SubLocation": "",
                        "latitude": np.nan,
                        "longitude": np.nan,
                        "description": "",
                        "ControlledEnvironment":None,
                        "sensors": [],#"GOBI", "HIRES", "M3M"
                    },
                    ]
            },          
        }
        with open(pym_fn, "w") as f:
            yaml.dump(project_data, f, sort_keys=False)
        print(f"New Project YAML file created: {pym_fn}. Please edit it to add project and site information")
        # +++++ Add the file to the github repo +++++
        if not args.no_git:
            repo.git.add(pym_fn)
            gitmod = True   

    # +++++ Load the yaml file +++++
    Proj_data = yaml.safe_load(open(f"{pym_fn}", "r"))
    
    # breakpoint()
    if not args.no_git:
        gitmod = GitChanged(repo, pym_fn, gitmod)

    # breakpoint()
    return Proj_data, gitmod


def _df_col_check(dfx, fname, colnms, args, repo, gitmod, fill_val=None):
    """
    Ensure DataFrame has required columns and is tracked by git.

    Parameters
    ----------
    dfx : pandas.DataFrame
        DataFrame to check.
    fname : str
        Path to the CSV file.
    colnms : list of str
        Required column names.
    args : argparse.Namespace
        Parsed command-line arguments.
    repo : git.Repo
        GitPython Repo object for git operations.
    gitmod : bool
        Flag indicating if the git repo has been modified.
    fill_val : any, optional
        Value to fill for missing columns (default is None).

    Returns
    -------
    dfx : pandas.DataFrame
        DataFrame with required columns.
    gitmod : bool
        Updated git modification flag.

    Notes
    -----
    - Adds missing columns with fill_val.
    - Adds file to git if enabled.
    """
    # +++++ Do a column name check and a repo check +++++
    #  Do column check and add missing columns if needed.

    if not (dfx.columns.tolist() == colnms) :
        # +++++ Column missmatch +++++
        missing_cols = set(colnms) - set(dfx.columns)
        # breakpoint()
        # +++++ Add the missing columns to the DataFrame with a default value +++++
        if not missing_cols == {}:
            print(f"col missing in: {fname}. Fix applied by adding: {missing_cols}")
            for col in missing_cols:
                dfx[col] = fill_val
            # ===== Reorder and save =====
            dfx = dfx[colnms]
            dfx.to_csv(fname, index=False)
        if not args.no_git:
            repo.git.add(fname)
            gitmod = True
    # +++++ Check if the file is in the repo +++++
    if not args.no_git:
        # +++++ che both the repo and the staged area +++++
        if not (fileInRepo(repo, fname) or is_file_staged(repo, fname)):
            print(f"File: {fname} is not in the git repo. Adding it to the repo")
            repo.git.add(fname)
            gitmod = True

    return dfx, gitmod


def _sitenamemaker(site, psyl_fname=""):
    """
    Generate a standardized site name based on year and controlled environment status.

    Parameters
    ----------
    site : dict
        Dictionary containing site information.
    psyl_fname : str, optional
        Path to the project YAML file (for error reporting).

    Returns
    -------
    sitename : str
        Standardized site name.

    Raises
    ------
    ValueError
        If ControlledEnvironment is not True, False, or None.
    """
    sitename = f"{site['year']}{site['name']}"
    # ===== Check the Site is a controlled environment =====
    if not site["ControlledEnvironment"] is None:
        if not site["ControlledEnvironment"] in [True, False]:
            raise ValueError(f"Site: {site['name']} has an invalid ControlledEnvironment: {site['ControlledEnvironment']}. Must be True, False or null. Setting to False. File: {psyl_fname}")
        elif site["ControlledEnvironment"]:
            sitename = f"{sitename}_C" # Controlled environment
        else:
            sitename = f"{sitename}_F" # Field Site
    return sitename

# ==============================================================================
def Rowchecker(flog_fname, flrow, prow, ProjectInfo, historical, past_date=(pd.Timestamp.now()-pd.Timedelta(days=14))):
    """
    Validate a row from the field log for correctness and consistency.

    Parameters
    ----------
    flog_fname : str
        Path to the field log file. Used for error reporting.
    flrow : pandas.Series
        The field log row to be checked.
    prow : pandas.Series
        The project row to be checked. Used to verify valid sensors.
    ProjectInfo : dict
        Project information dictionary containing project details.
    historical : bool
        Whether to allow dates earlier than the default past_date.
    past_date : pandas.Timestamp, optional
        The earliest allowed date for the log entry. Defaults to 14 days before the current date.

    Returns
    -------
    check : float or None
        The computed checksum for the row if it needs to be updated, or None if already valid.
    site : dict
        The site dictionary matching the row's site.

    Raises
    ------
    ValueError
        If any validation check fails.

    Notes
    -----
    - Checks data types, date validity, sensor validity, and run count.
    - Computes and verifies a checksum for row integrity.
    - Designed to be extended for additional checks.
    """

    def _ErrorMessage(error_message, flog_fname, flrow, nl = '\n'):
        """
        Internal function to make a standard error message
        """
        raise ValueError(f"Problem in Field Log: {flog_fname}{nl}Issue in row:{nl}{flrow}{nl}{error_message}")

    # ========== Do the Hashing of the data ==========
    hashes = pd.util.hash_pandas_object(flrow.drop("CheckSum"))
    check  = float(hashes.sum() % 100000000) # Using the % because the numbers were too big and were getting corrupted by the csv
    if not np.isnan(flrow.CheckSum):
        # Make sure the checksum matches
        if not check == flrow.CheckSum:
            print(f"CheckSum doesn't match in {flog_fname}. {flrow}, Check: {check} This feature has not been implemented yet. Going interactive")
            breakpoint()
            # TO DO: ADD ome command line arguments here
            # sys.exit()
        else:
            # Make the check = None to indicate its already done
            check = None

    # ========== Check all the dtypes rows ==========
    for vname in ["Year", "Month", "Day", "Runs"]:
        if not type(flrow[vname]) == int:
            _ErrorMessage(f"dtype for {vname} must be int, current dytpe {type(flrow[vname])}", flog_fname, flrow)

    for sname in ["Technician", "Sensor", "Site"]:
        if not type(flrow[sname]) == str:
            _ErrorMessage(f"dtype for {sname} must be str, current dytpe {type(flrow[sname])}", flog_fname, flrow)


    # ========== Check the date of the row ==========
    try:
        date = pd.Timestamp(f"{flrow.Year}-{flrow.Month}-{flrow.Day}")
    except Exception as er:
        _ErrorMessage(f"{str(er)}", flog_fname, flrow)

    # +++++ Check if the date is in the future or past +++++
    if not check is None:
        # Skip the datacheck in case of already complete data
        if date > (pd.Timestamp.now() + pd.Timedelta(hours=12)):
            _ErrorMessage(f"Row Date: {date} is greater than system current time {pd.Timestamp.now()}. Future Dates Not allowed", flog_fname, flrow)
        elif date < past_date:
            if not historical:
                _ErrorMessage(f"Row Date: {date} is before than max historical date {past_date}. run 'python ProjectBuilder.py --historical' to allow past dates", flog_fname, flrow)
    
    # ========== Check if the sensor is valid ==========
    if not flrow.Sensor in prow[prow == True].index:
        _ErrorMessage(f"Sensor: {flrow.Sensor} is not in the valid sensors for this project({prow[prow == True].index}). Edit Projects_Summary.csv to add sensors", flog_fname, flrow)

    # ========== Check the number of runs ==========
    if flrow.Runs < 1:
        _ErrorMessage(f"The number of runs: {flrow.Runs} Must be greater than 0", flog_fname, flrow)
    # ========== Check the site name and year ==========
    if not flrow.Site in [site["name"] for site in  ProjectInfo["project"]["sites"]]:
        _ErrorMessage(f"Site: {flrow.Site} is not in the valid sites for this project({ProjectInfo['project']['sites']}). Edit the ProjectSummary.yaml in the project folder to add sites", flog_fname, flrow)
    else:
        # +++++ Check the site year matches row year +++++
        errorlog = "" # COntiner for error messages
        outsite = None
        for site in ProjectInfo["project"]["sites"]:

            if site["name"] == flrow.Site:
                if not site["year"] == flrow.Year:
                    errorlog += f"Site: {flrow.Site} has year: {site['year']} but row has year: {flrow.Year}. Please edit the project yaml file to fix this"
                    continue
                else:
                    outsite = site
                    break
            # This whould only be reached if the site is not found
        if outsite is None:
            _ErrorMessage(errorlog, flog_fname, flrow)
        # breakpoint()
    return check, outsite

def pymkdir(path):
    """
    Create a directory if it does not already exist.

    Parameters
    ----------
    path : str
        The directory path to create.

    Returns
    -------
    None

    Notes
    -----
    If the directory already exists, nothing happens.
    """
    if not os.path.exists(path):
        print(path)
        os.makedirs(path)

def is_file_staged(repo, filepath):
    """
    Check if a file is staged (added to the index) in the given git repository.

    Parameters
    ----------
    repo : git.Repo
        A GitPython Repo object.
    filepath : str
        Path to the file (relative to repo root).

    Returns
    -------
    bool
        True if the file is staged, False otherwise.
    """
    # Remove leading './' for consistency
    relpath = filepath.replace("./", "")
    # Check if file is in the index but not in HEAD (i.e., staged for commit)
    staged_files = [item.a_path for item in repo.index.diff("HEAD")]
    return relpath in staged_files

def fileInRepo(repo, filePathIN):
    """
    Check if a file exists in the given git repository.

    Parameters
    ----------
    repo : git.Repo
        A GitPython Repo object.
    filePathIN : str
        The file path (relative to the repository root).

    Returns
    -------
    bool
        True if the file exists in the repository, False otherwise.

    Notes
    -----
    The function removes leading './' from the path for compatibility with git.
    """
    filePath = filePathIN.replace("./", '') # git doesnt have the ./ in paths
    pathdir = os.path.dirname(filePath)

    # Build up reference to desired repo path
    rsub = repo.head.commit.tree

    for path_element in pathdir.split(os.path.sep):

        # If dir on file path is not in repo, neither is file. 
        try : 
            rsub = rsub[path_element]

        except KeyError : 
            return False
    return(filePath in rsub)

def GitChanged(repo, fname, gitmod):
    """
    Check if a file has been modified in the git repository and stage it if so.

    Parameters
    ----------
    repo : git.Repo
        A GitPython Repo object.
    fname : str
        The file name to check.
    gitmod : bool
        Current git modification flag.

    Returns
    -------
    gitmod : bool
        Updated git modification flag.
    """
    # +++++ Check if the file is in the repo +++++
    if not fileInRepo(repo, fname):
        print(f"WARNING. File: {fname} is not in the git repo. Adding it to the repo")
        repo.git.add(fname)
        gitmod = True

    unstaged_diffs = repo.index.diff(None)
    # ========== Loop over the difs ==========
    for diff in unstaged_diffs:
        # +++++ Check if the dif matches the file +++++
        if diff.a_path == fname.replace("./", '') or diff.b_path == fname.replace("./", ''):
            # File has been modified
            if diff.change_type == 'M':
                repo.git.add(fname)
                gitmod = True
            else:
                print(f"WARNING. File: {fname} has been modified but the change type in not M. Change type:{diff.change_type}. File Not added to repo")
            break # Exit the loop as we found the file
    return gitmod

def GitPull(repo):
    """Pulls the latest changes from a given Git repository.

    This function attempts to update the local repository by pulling the latest changes
    from the remote. If the repository is not up to date after the pull, it notifies the user,
    prints the pull log, and exits the script. There is a placeholder for adding an option
    to skip this check in the future.

    Parameters
    ----------
    repo : git.Repo
        The GitPython Repo object representing the repository to pull from.

    Returns
    -------
    None

    Raises
    ------
    SystemExit
        If the repository is not up to date after the pull operation.

    """

    print(f"Starting git pull of the repo at: {pd.Timestamp.now()}")
    pull_log = repo.git.pull()

    # TO DO: Add a way to force skip this check 
    if not pull_log == 'Already up to date.':
        print("The remote git repo is not in sync")
        print(f"sync log: {pull_log}")
        print("Please rerun the script. if there are repeat errors there might be a git or connection issue. Script can be run with --no-git to skip pull")
        breakpoint()
        sys.exit()


# ==================================================================================
if __name__ == '__main__':

    # ========== Set the args Description ==========
    description='Optional Command line arguments for script'
    parser = argparse.ArgumentParser(description=description)

    # ========== Add the command line arguments ==========   
    parser = argparse.ArgumentParser(description="Generate dataset folder structure.")
    parser.add_argument("--no-git", action="store_true", help="Disable git operations.")
    # parser.add_argument("--node", type=str, default="Narrabri", help="Node name.")
    # parser.add_argument("--projects-csv", type=str, default="./Projects_Summary.csv", help="Projects summary CSV path.")
    parser.add_argument("--projectsYAML", type=str, default="./NodeSummary.yaml", help="the node yaml file with the sensors.")
    parser.add_argument("-p","--historical", action="store_true", help="Allow historical data")
    
    args = parser.parse_args()

    # +++++ Check the paths and set exc path to the root of the git folder +++++
    if not args.no_git:
        path = os.getcwd()
        try:
            git_repo = git.Repo(path, search_parent_directories=True)
            git_root = git_repo.git.rev_parse("--show-toplevel")
        except git.exc.InvalidGitRepositoryError:
            raise git.exc.InvalidGitRepositoryError(f"This script was called from an unknown path ({path}). Must be in a git repo")
        finally:
            sys.path.append(git_root)

        # # +++++ Check if the repo is up to date +++++
        repo = git.Repo(git_root)
    else:
        repo = None
    
    # ========== Parse Args to main function ==========
    main(args, repo)

