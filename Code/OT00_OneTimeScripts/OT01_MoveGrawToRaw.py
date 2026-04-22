"""Move ``*.graw`` folders from ``T1_proc`` into the adjacent ``T0_raw``.

This one-time script targets only GOBI and CALVIS sensors. It walks a
root directory, locates ``T1_proc`` folders that sit beneath a sensor
folder whose name contains ``GOBI`` or ``CALVIS``, and moves any direct
child folders ending in ``.graw`` into the sibling ``T0_raw`` folder
(created if missing).

Layout assumption
-----------------
``.../<sensor>/<date>/run_XX/T1_proc/<something>.graw`` becomes
``.../<sensor>/<date>/run_XX/T0_raw/<something>.graw``.

Command line
------------
``--path PATH``
    Optional root directory to search. When supplied, the git repository
    check is skipped and only that directory is scanned.
``--dry-run``
    List candidate moves without performing them.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

SENSOR_KEYWORDS = ('GOBI', 'CALVIS')


def main():
    """Entry point for the script.

    Parses command line arguments, determines the search root, finds
    candidate ``.graw`` folders, prompts for confirmation (unless
    ``--dry-run`` is set) and performs the moves.

    Returns
    -------
    None
        The function prints progress information and exits via
        :func:`sys.exit` on fatal errors.
    """
    parser = argparse.ArgumentParser(
        description=("Move '*.graw' folders from T1_proc into the adjacent "
                     "T0_raw folder for GOBI and CALVIS sensors."),
    )
    parser.add_argument(
        '--path',
        type=str,
        default=None,
        help=('Optional root directory to search. When provided, the git '
              'repository check is skipped and only this directory is '
              'scanned for matching .graw folders.'),
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List what would be moved without performing any moves.',
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Move .graw folders: T1_proc -> T0_raw (GOBI / CALVIS)")
    print("=" * 60)

    if args.path is not None:
        root_path = Path(args.path).expanduser().resolve()
        if not root_path.is_dir():
            print(f"Error: Provided path is not a directory: {root_path}")
            sys.exit(1)
        print(f"Using provided path (git check skipped): {root_path}")
    else:
        root_path = get_git_root()
        if root_path is None:
            sys.exit(1)
        print(f"Git repository root: {root_path}")

    print("\nSearching for '*.graw' folders inside GOBI/CALVIS T1_proc folders...")
    matches = find_graw_folders(root_path)

    if not matches:
        print("No '.graw' folders found to move.")
        return

    print(f"Found {len(matches)} '.graw' folder(s):")
    for src, dst in matches:
        print(f"  - {src}")
        print(f"      -> {dst}")

    if args.dry_run:
        print("\nDry run requested. No changes made.")
        return

    response = input(
        f"\nProceed with moving {len(matches)} folder(s)? (y/N): "
    ).strip().lower()
    if response not in ('y', 'yes'):
        print("Operation cancelled.")
        return

    print("\nMoving folders...")
    success_count = 0
    failure_count = 0
    failures = []
    progress = tqdm(matches, desc="Moving .graw", unit="folder")
    for src, dst in progress:
        progress.set_postfix_str(src.name)
        ok, message = move_graw_folder(src, dst)
        if ok:
            success_count += 1
        else:
            failure_count += 1
            failures.append(message)
            tqdm.write(f"\u2717 {message}")

    print("\n" + "=" * 60)
    print("Move completed!")
    print(f"Successfully moved: {success_count}")
    print(f"Failed: {failure_count}")
    print("=" * 60)


def get_git_root():
    """Return the root directory of the current git repository.

    Returns
    -------
    pathlib.Path or None
        Absolute path to the repository root, or ``None`` if the current
        working directory is not inside a git repository or the ``git``
        executable is not available.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository or git not available")
        return None
    except FileNotFoundError:
        print("Error: Git command not found")
        return None


def has_sensor_ancestor(path):
    """Check whether ``path`` lives under a GOBI or CALVIS sensor folder.

    The sensor folder typically sits a few levels above ``T1_proc``, e.g.
    ``.../<sensor>/<date>/run_XX/T1_proc/<name>.graw``.

    Parameters
    ----------
    path : pathlib.Path
        Path whose ancestor chain is inspected.

    Returns
    -------
    bool
        ``True`` if any ancestor folder name (case-insensitive) contains
        one of :data:`SENSOR_KEYWORDS`, ``False`` otherwise.
    """
    for parent in path.parents:
        upper = parent.name.upper()
        if any(keyword in upper for keyword in SENSOR_KEYWORDS):
            return True
    return False


def find_graw_folders(root_path):
    """Find ``.graw`` folders to move under ``root_path``.

    The function walks ``root_path`` and selects directories named
    ``T1_proc`` whose ancestry includes a GOBI or CALVIS sensor folder.
    For each such ``T1_proc`` it collects the direct child folders whose
    name ends in ``.graw`` and pairs them with their target location in
    the sibling ``T0_raw`` folder.

    Parameters
    ----------
    root_path : pathlib.Path or str
        Directory to search recursively.

    Returns
    -------
    list of tuple of pathlib.Path
        A list of ``(source, destination)`` pairs where ``source`` is the
        existing ``.graw`` folder inside ``T1_proc`` and ``destination``
        is the proposed location inside the adjacent ``T0_raw`` folder.
    """
    matches = []

    for dirpath, dirnames, _ in os.walk(root_path):
        current = Path(dirpath)

        # We only care when we are inside a T1_proc folder
        if current.name != 'T1_proc':
            continue

        # Must live under a GOBI/CALVIS sensor folder somewhere up the tree
        if not has_sensor_ancestor(current):
            dirnames[:] = []
            continue

        # Adjacent (sibling) T0_raw folder
        t0_raw = current.parent / 'T0_raw'

        for dname in list(dirnames):
            if dname.endswith('.graw'):
                matches.append((current / dname, t0_raw / dname))

        # Don't descend further; .graw folders should be direct children
        dirnames[:] = []

    return matches


def move_graw_folder(src, dst):
    """Move a single ``.graw`` folder from ``src`` to ``dst``.

    Parameters
    ----------
    src : pathlib.Path
        Existing source folder to move.
    dst : pathlib.Path
        Destination folder path. Its parent directory is created if it
        does not already exist. If ``dst`` already exists, the move is
        aborted to avoid overwriting data.

    Returns
    -------
    tuple of (bool, str)
        ``(success, message)`` where ``success`` is ``True`` when the
        folder was moved and ``False`` otherwise. ``message`` describes
        the outcome and is suitable for logging.
    """
    try:
        if dst.exists():
            return False, f"Target already exists: {dst}"

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return True, f"Moved: {src} -> {dst}"
    except Exception as e:
        return False, f"Failed to move {src}: {e}"


if __name__ == "__main__":
    main()
