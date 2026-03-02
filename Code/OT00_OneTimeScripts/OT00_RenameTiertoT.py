"""
Script to rename folders starting with 'Tier' to start with 'T' instead.
Example: Tier0_raw -> T0_raw

This script:
1. Finds the git repository root
2. Recursively searches for directories starting with 'Tier'
3. Renames them to start with 'T' instead
4. Provides a summary of changes made
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_git_root():
    """Get the root directory of the git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository or git not available")
        return None
    except FileNotFoundError:
        print("Error: Git command not found")
        return None


def find_tier_folders(root_path):
    """Find all directories starting with 'Tier' recursively."""
    tier_folders = []
    
    try:
        for root, dirs, files in os.walk(root_path):
            # Create a copy of dirs to avoid modifying during iteration
            dirs_copy = dirs.copy()
            for dirname in dirs_copy:
                if dirname.startswith('Tier'):
                    full_path = Path(root) / dirname
                    tier_folders.append(full_path)
                    # Remove from dirs to prevent walking into renamed directories
                    # This avoids issues if we rename during the search
                    # dirs.remove(dirname)
        
    except Exception as e:
        print(f"Error searching for directories: {e}")
    
    return tier_folders


def rename_tier_to_t(folder_path):
    """Rename a folder from 'Tier...' to 'T...'"""
    try:
        parent_dir = folder_path.parent
        old_name = folder_path.name
        new_name = 'T' + old_name[4:]  # Remove 'Tier' (4 chars) and add 'T'
        new_path = parent_dir / new_name
        
        # Check if target already exists
        if new_path.exists():
            print(f"Warning: Target already exists: {new_path}")
            return False, f"Target {new_path} already exists"
        
        # Perform the rename
        folder_path.rename(new_path)
        return True, f"Renamed: {folder_path} -> {new_path}"
        
    except Exception as e:
        return False, f"Failed to rename {folder_path}: {e}"


def main():
    """Main function to execute the renaming process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Rename folders starting with 'Tier' to start with 'T' instead.",
        epilog="Example: Tier0_raw -> T0_raw"
    )
    parser.add_argument(
        '--path', 
        type=str, 
        help='Optional path to search for Tier folders. If not provided, uses git repository root.'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Tier to T Folder Renaming Script")
    print("=" * 60)
    
    # Determine the root path to use
    if args.path:
        root_path = Path(args.path)
        if not root_path.exists():
            print(f"Error: Provided path does not exist: {root_path}")
            sys.exit(1)
        if not root_path.is_dir():
            print(f"Error: Provided path is not a directory: {root_path}")
            sys.exit(1)
        print(f"Using provided path: {root_path}")
    else:
        # Get git repository root
        root_path = get_git_root()
        if not root_path:
            sys.exit(1)
        print(f"Git repository root: {root_path}")
    
    # Find all Tier folders
    print("\nSearching for folders starting with 'Tier'...")
    tier_folders = find_tier_folders(root_path)
    
    if not tier_folders:
        print("No folders starting with 'Tier' found.")
        return
    
    print(f"Found {len(tier_folders)} folder(s) starting with 'Tier':")
    for folder in tier_folders:
        print(f"  - {folder}")
    
    # Ask for confirmation
    print(f"\nThis will rename {len(tier_folders)} folder(s).")
    response = input("Do you want to proceed? (y/N): ").strip().lower()
    
    if response not in ['y', 'yes']:
        print("Operation cancelled.")
        return
    
    # Perform renaming
    print("\nRenaming folders...")
    success_count = 0
    failure_count = 0
    
    for folder in tier_folders:
        success, message = rename_tier_to_t(folder)
        if success:
            success_count += 1
            print(f"✓ {message}")
        else:
            failure_count += 1
            print(f"✗ {message}")
    
    print("\n" + "=" * 60)
    print(f"Renaming completed!")
    print(f"Successfully renamed: {success_count}")
    print(f"Failed: {failure_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
