# DataStorage Project

This repository provides a data structure and automation scripts for managing data storage across APPN application nodes. It is designed to streamline and automate the creation of folders, project logs, and metadata files for research projects, sites, and sensor platforms.

## Features

- **Automated Folder Creation:** Scripts to generate and organize folders for projects, sites, and sensors.
- **YAML/JSON Metadata:** Templates and tools for maintaining project, researcher, and site metadata in YAML and JSON formats.
- **Git Integration:** Optional git version control for tracking changes to folders and metadata.
- **Customizable Structure:** Easily adapt the folder and metadata structure to suit different research needs.


## Getting Started

1. **fork the repository:**
   - Clone a copy of your forked repo
   ```bash
   git clone <repo-url>
   ```
2. **Setup a Conda environemnt**
   ```bash
   conda create -n datastorage python=3.12 numpy pandas pyyaml gitpython git
   conda activate datastorage
   ```


3. **Configure your nodes and projects:**
   - Edit `NodeSummary.yaml` to define your nodes and sensor platforms.


4. **Run the automation script:**
   ```bash
   python ProjectBuilder.py
   ```
5. **Add info to the project_summary.csv**
   - Add details to the project summary csv found in the node folder. The should be in the form of TRUE and FALSE depending on if a project uses a given sensor.  
   - Project name should follow the format in FolderStructure.txt
   ```bash
   python ProjectBuilder.py
   ```
   - Edit or generate `ProjectInfo.yaml` for project, researcher, and site metadata.

## File Descriptions

- **ProjectBuilder.py:** Main script for automating folder and metadata creation.
- **NodeSummary.yaml:** YAML file listing nodes and their sensor platforms.
- **_node_Projects_Summary.csv:** CSV file summarizing projects and their associated sensors.
- **ProjectInfo.yaml:** YAML file containing detailed project, researcher, and site information.
- **README.md:** This documentation file.


## License

[MIT License](LICENSE)

## Contact

For questions or contributions, please contact the repository maintainer.
