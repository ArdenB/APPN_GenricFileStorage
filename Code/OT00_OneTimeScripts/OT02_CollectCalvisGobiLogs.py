"""Collect log/config files from CALVIS and GOBI ``.graw``/``.gpro`` folders.

This one-time script walks a search directory, locates ``.graw`` and
``.gpro`` folders that sit beneath a sensor folder whose name contains
``CALVIS`` or ``GOBI``, and copies a curated set of log/configuration
files into a single output directory so they can be sent for review.

Output layout
-------------
Each source ``.graw``/``.gpro`` folder is collapsed into a single
labelled folder in the output directory, named
``<SENSOR>_<KIND>_<NN>`` (e.g. ``CALVIS_GRAW_00``, ``GOBI_GPRO_03``).
Files from the original folder (with their relative subpaths inside it)
are copied beneath that labelled folder.

A ``manifest.csv`` is written at the root of the output directory.
In addition to identifying each collected folder, it records whether
the source folder follows the APPN folder structure (see
https://github.com/ArdenB/APPN_GenricFileStorage/wiki) using
:func:`parse_APPN_dataset_path`. Columns:

``sensor, kind, number, label, source_path, output_path,
appn_valid, appn_errors, node, project, site_folder, year, sensor_folder,
date, run_folder, run, tier, sub_tier``.

Files collected
---------------
From each ``*.graw`` folder:

* ``mission_data.yaml``
* ``targets.yaml``
* ``elm_coefficients.json``
* ``HP-*/settings.txt``
* ``uVS-*/settings.txt``
* ``SBG/export_*.txt``
* ``APX-15/export_*.txt``

From each ``*.gpro`` folder:

* ``products.yaml``
* ``pipelines/*.yml``
* ``processing_logs/*.txt``

Command line
------------
``--path PATH [PATH ...]``
    One or more root directories to search. May be repeated or given
    as a space-separated list. Defaults to the current git repository
    root. When multiple paths are supplied the results are merged into
    a single output directory with a single ``manifest.csv``.
``--dest PATH``
    Output directory for the collected logs and ``manifest.csv``.
    Defaults to ``<root>/GRYFN_logs`` where ``<root>`` is the first
    ``--path`` if provided, otherwise the git repository root.
``--dry-run``
    List candidate copies without performing them.
"""

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

# Make the repository root importable so we can use the shared APPN path
# parser. The script lives in ``Code/OT00_OneTimeScripts``; the repo root
# is two levels above.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from Code.functions.core_functions.parse_APPN_dataset_path import (  # noqa: E402
    parse_APPN_dataset_path,
)

SENSOR_KEYWORDS = ('CALVIS', 'GOBI')

# (subdir relative to .graw root, glob within that subdir)
GRAW_PATTERNS = [
    ('', 'mission_data.yaml'),
    ('', 'targets.yaml'),
    ('', 'elm_coefficients.json'),
    ('HP-*', 'settings.txt'),
    ('uVS-*', 'settings.txt'),
    ('SBG', 'export_*.txt'),
    ('APX-15', 'export_*.txt'),
]

GPRO_PATTERNS = [
    ('', 'products.yaml'),
    ('pipelines', '*.yml'),
    ('processing_logs', '*.txt'),
]


def main():
    """Run the log-collection workflow.

    Parses command-line arguments, scans one or more search roots for
    CALVIS/GOBI ``.graw`` and ``.gpro`` folders, builds a copy plan,
    prompts for confirmation (unless ``--dry-run`` is set) and copies
    the curated log/config files to the destination, writing a
    ``manifest.csv`` alongside.

    Returns
    -------
    None
        Side-effecting entry point. Exits the process via
        :func:`sys.exit` on argument or filesystem errors.
    """
    args = _parse_args()
    _print_banner()

    root_paths = _resolve_search_roots(args.path)
    dest_root = _resolve_dest_root(args.dest, root_paths)
    print(f"Destination: {dest_root}")

    folders = _scan_for_target_folders(root_paths)
    if not folders:
        print("No matching .graw/.gpro folders found.")
        return

    _annotate_folders(folders, dest_root)
    _print_scan_summary(folders)

    copies = _build_copy_plan(folders)
    if not copies:
        print("No matching files found inside any folders.")
        return

    _print_copy_preview(copies)

    if args.dry_run:
        _print_dry_run_summary(folders)
        return

    if not _confirm(f"\nProceed with copying {len(copies)} file(s) "
                    f"to {dest_root}? (y/N): "):
        print("Operation cancelled.")
        return

    dest_root.mkdir(parents=True, exist_ok=True)
    success_count, failure_count = _execute_copies(copies)

    manifest_path = dest_root / 'manifest.csv'
    write_manifest(manifest_path, folders)

    _print_completion(success_count, failure_count, dest_root, manifest_path)


def _parse_args():
    """Parse command-line arguments for :func:`main`.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with attributes ``path``, ``dest`` and
        ``dry_run``.
    """
    parser = argparse.ArgumentParser(
        description=("Collect log/config files from CALVIS and GOBI "
                     ".graw and .gpro folders into a single directory."),
    )
    parser.add_argument('--path', type=str, default=None, nargs='+',
                        action='extend',
                        help=('One or more root directories to search. '
                              'May be repeated. Defaults to the current '
                              'git repository root.'))
    parser.add_argument('--dest', type=str, default=None,
                        help=('Output directory for collected logs. '
                              'Defaults to <root>/GRYFN_logs.'))
    parser.add_argument('--dry-run', action='store_true',
                        help='List what would be copied without copying.')
    return parser.parse_args()


def _print_banner():
    """Print the script banner to stdout."""
    print("=" * 60)
    print("Collect CALVIS / GOBI logs from .graw and .gpro folders")
    print("=" * 60)


def _resolve_search_roots(raw_paths):
    """Resolve and de-duplicate the user's ``--path`` argument.

    Parameters
    ----------
    raw_paths : list of str or None
        Raw values from ``args.path``. If empty/``None`` the function
        falls back to the git repository root.

    Returns
    -------
    list of pathlib.Path
        Existing, resolved, de-duplicated search roots in the order
        the user provided them.
    """
    if raw_paths:
        roots = []
        for raw in raw_paths:
            p = Path(raw).expanduser().resolve()
            if not p.is_dir():
                print(f"Error: Search path is not a directory: {p}")
                sys.exit(1)
            roots.append(p)
        seen = set()
        roots = [p for p in roots if not (p in seen or seen.add(p))]
        print("Search paths (provided):")
        for p in roots:
            print(f"  {p}")
        return roots

    git_root = get_git_root()
    if git_root is None:
        sys.exit(1)
    print(f"Search path (git root): {git_root}")
    return [git_root]


def _resolve_dest_root(raw_dest, root_paths):
    """Determine the output directory.

    Parameters
    ----------
    raw_dest : str or None
        Raw value from ``args.dest``.
    root_paths : list of pathlib.Path
        Resolved search roots; the first is used to build the default
        when ``raw_dest`` is ``None``.

    Returns
    -------
    pathlib.Path
        Resolved destination directory (not necessarily existing yet).
    """
    if raw_dest is not None:
        return Path(raw_dest).expanduser().resolve()
    return root_paths[0] / 'GRYFN_logs'


def _scan_for_target_folders(root_paths):
    """Scan every search root for ``.graw``/``.gpro`` folders.

    Records found across multiple roots are de-duplicated by their
    resolved source path so the same folder is never collected twice.

    Parameters
    ----------
    root_paths : list of pathlib.Path
        Search roots to walk.

    Returns
    -------
    list of dict
        Folder records as produced by :func:`find_target_folders`,
        each annotated with a ``search_root`` key naming the root that
        discovered it.
    """
    print("\nSearching for CALVIS/GOBI '.graw' and '.gpro' folders...")
    folders = []
    seen_sources = set()
    for root_path in root_paths:
        print(f"  scanning {root_path} ...")
        for rec in find_target_folders(root_path):
            src = rec['source'].resolve()
            if src in seen_sources:
                continue
            seen_sources.add(src)
            rec['search_root'] = root_path
            folders.append(rec)
    return folders


def _annotate_folders(folders, dest_root):
    """Sort, label and APPN-validate each folder record in-place.

    Each record gains the keys ``number``, ``label``, ``out_dir`` and
    ``appn``. Labels are zero-padded to a width of at least 2 digits
    (or wider if needed for the largest sensor/kind bucket).

    Parameters
    ----------
    folders : list of dict
        Folder records produced by :func:`_scan_for_target_folders`.
    dest_root : pathlib.Path
        Output directory used to compute each record's ``out_dir``.

    Returns
    -------
    None
        The records are mutated in place.
    """
    folders.sort(key=lambda r: (r['sensor'], r['kind'], str(r['source'])))

    counters = {}
    for rec in folders:
        key = (rec['sensor'], rec['kind'])
        rec['number'] = counters.get(key, 0)
        counters[key] = rec['number'] + 1

    max_count = max(counters.values()) if counters else 1
    pad = max(2, len(str(max_count - 1)))
    for rec in folders:
        rec['label'] = (
            f"{rec['sensor']}_{rec['kind'].upper()}_{rec['number']:0{pad}d}"
        )
        rec['out_dir'] = dest_root / rec['label']
        rec['appn'] = validate_appn_path(rec['source'])


def _print_scan_summary(folders):
    """Print a count of discovered folders, broken down by kind.

    Parameters
    ----------
    folders : list of dict
        Annotated folder records (must have ``kind`` and ``appn`` keys).
    """
    n_invalid = sum(1 for r in folders if not r['appn'].get('valid'))
    if n_invalid:
        print(f"  WARNING: {n_invalid} folder(s) do not match the "
              "APPN folder structure (see manifest.csv).")

    n_graw = sum(1 for r in folders if r['kind'] == 'graw')
    n_gpro = sum(1 for r in folders if r['kind'] == 'gpro')
    print(f"  .graw folders: {n_graw}")
    print(f"  .gpro folders: {n_gpro}")


def _build_copy_plan(folders):
    """Build the full ``(src, dst)`` list for every folder record.

    Parameters
    ----------
    folders : list of dict
        Annotated folder records.

    Returns
    -------
    list of tuple of (pathlib.Path, pathlib.Path)
        Concatenated ``(src, dst)`` pairs across every record.
    """
    print("\nCollecting file list...")
    copies = []
    for rec in folders:
        patterns = GRAW_PATTERNS if rec['kind'] == 'graw' else GPRO_PATTERNS
        copies.extend(collect_from_folder(rec['source'], rec['out_dir'],
                                          patterns))
    return copies


def _print_copy_preview(copies, limit=20):
    """Print up to ``limit`` planned copy pairs.

    Parameters
    ----------
    copies : list of tuple of (pathlib.Path, pathlib.Path)
        Planned ``(src, dst)`` copy pairs.
    limit : int, optional
        Maximum number of pairs to display. Default is 20.
    """
    print(f"Found {len(copies)} file(s) to copy.")
    for src, dst in copies[:limit]:
        print(f"  - {src}")
        print(f"      -> {dst}")
    if len(copies) > limit:
        print(f"  ... ({len(copies) - limit} more)")


def _print_dry_run_summary(folders):
    """Print the per-folder APPN validation result for a dry run.

    Parameters
    ----------
    folders : list of dict
        Annotated folder records.
    """
    print("\nDry run requested. No changes made.")
    for rec in folders:
        status = 'OK' if rec['appn'].get('valid') else 'INVALID'
        print(f"  [{status}] {rec['label']}: {rec['source']}")
        for err in rec['appn'].get('errors') or []:
            print(f"      - {err}")


def _confirm(prompt):
    """Prompt the user for a y/N confirmation.

    Parameters
    ----------
    prompt : str
        Prompt text shown to the user.

    Returns
    -------
    bool
        ``True`` if the user answered ``y`` or ``yes``
        (case-insensitive), ``False`` otherwise.
    """
    return input(prompt).strip().lower() in ('y', 'yes')


def _execute_copies(copies):
    """Copy every planned file with a progress bar.

    Parameters
    ----------
    copies : list of tuple of (pathlib.Path, pathlib.Path)
        Planned ``(src, dst)`` copy pairs.

    Returns
    -------
    success_count : int
        Number of files copied successfully.
    failure_count : int
        Number of files that failed to copy.
    """
    print("\nCopying files...")
    success_count = 0
    failure_count = 0
    progress = tqdm(copies, desc="Copying", unit="file")
    for src, dst in progress:
        progress.set_postfix_str(src.name)
        ok, message = copy_file(src, dst)
        if ok:
            success_count += 1
        else:
            failure_count += 1
            tqdm.write(f"\u2717 {message}")
    return success_count, failure_count


def _print_completion(success_count, failure_count, dest_root, manifest_path):
    """Print the final completion summary block.

    Parameters
    ----------
    success_count : int
        Number of files copied successfully.
    failure_count : int
        Number of files that failed to copy.
    dest_root : pathlib.Path
        Output directory.
    manifest_path : pathlib.Path
        Path to the written manifest CSV.
    """
    print("\n" + "=" * 60)
    print("Copy completed!")
    print(f"Successfully copied: {success_count}")
    print(f"Failed: {failure_count}")
    print(f"Output directory:    {dest_root}")
    print(f"Manifest:            {manifest_path}")
    print("=" * 60)


def get_git_root():
    """Return the root directory of the current git repository.

    Runs ``git rev-parse --show-toplevel`` in the current working
    directory.

    Returns
    -------
    pathlib.Path or None
        Resolved path to the repository root, or ``None`` if the
        current directory is not inside a git repository or the
        ``git`` executable is not available. An error message is
        printed to stdout in the failure cases.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository or git not available")
        return None
    except FileNotFoundError:
        print("Error: Git command not found")
        return None


def has_sensor_ancestor(path):
    """Return the matched sensor keyword for ``path``, or ``None``.

    Walks ``path``'s ancestors and returns the first keyword from
    :data:`SENSOR_KEYWORDS` found in an ancestor folder name
    (case-insensitive).

    Parameters
    ----------
    path : pathlib.Path
        Path whose ancestors should be inspected.

    Returns
    -------
    str or None
        The matched sensor keyword (e.g. ``'CALVIS'`` or ``'GOBI'``),
        or ``None`` if no ancestor folder name contains a known sensor
        keyword.
    """
    for parent in path.parents:
        upper = parent.name.upper()
        for keyword in SENSOR_KEYWORDS:
            if keyword in upper:
                return keyword
    return None


def find_target_folders(root_path):
    """Find ``.graw`` and ``.gpro`` folders under CALVIS/GOBI sensors.

    Uses :func:`os.walk` and prunes traversal once a target folder is
    found (so the potentially huge contents of ``.graw``/``.gpro`` are
    never descended into) and skips Synology metadata folders.

    Parameters
    ----------
    root_path : pathlib.Path
        Directory to scan recursively.

    Returns
    -------
    list of dict
        One record per discovered target folder. Each record has keys:

        - ``sensor`` (str): sensor keyword from
          :data:`SENSOR_KEYWORDS` matched in an ancestor folder name.
        - ``kind`` (str): either ``'graw'`` or ``'gpro'``.
        - ``source`` (:class:`pathlib.Path`): absolute path to the
          discovered folder.
    """
    import os

    records = []
    skip_dirs = {'@eaDir', '.git', '#recycle', 'Vault'}
    for dirpath, dirnames, _ in os.walk(root_path):
        # Prune obvious noise.
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]

        keep = []
        for name in dirnames:
            current = Path(dirpath) / name
            if name.endswith('.graw'):
                kind = 'graw'
            elif name.endswith('.gpro'):
                kind = 'gpro'
            else:
                keep.append(name)
                continue
            sensor = has_sensor_ancestor(current)
            if sensor is not None:
                records.append({'sensor': sensor, 'kind': kind,
                                'source': current})
            # Do not descend into .graw / .gpro folders.
        dirnames[:] = keep
    return records


def collect_from_folder(folder, out_dir, patterns):
    """Build ``(src, dst)`` pairs for files inside ``folder``.

    For each ``(subdir_glob, file_glob)`` pattern, expands
    ``subdir_glob`` against ``folder`` (an empty string means
    ``folder`` itself), then matches ``file_glob`` against each
    resulting subdirectory and emits a copy pair preserving the
    relative path inside ``folder``.

    Parameters
    ----------
    folder : pathlib.Path
        A ``.graw`` or ``.gpro`` folder.
    out_dir : pathlib.Path
        Labelled output folder for this source folder.
    patterns : list of tuple of (str, str)
        ``(subdir_glob, file_glob)`` pairs to look for inside
        ``folder``. An empty ``subdir_glob`` targets ``folder``
        itself.

    Returns
    -------
    list of tuple of (pathlib.Path, pathlib.Path)
        ``(src, dst)`` pairs ready to pass to :func:`copy_file`.
    """
    pairs = []
    for subdir_glob, file_glob in patterns:
        if subdir_glob == '':
            sub_iter = [folder]
        else:
            sub_iter = [p for p in folder.glob(subdir_glob) if p.is_dir()]
        for sub in sub_iter:
            for src in sub.glob(file_glob):
                if not src.is_file():
                    continue
                try:
                    rel_in_folder = src.relative_to(folder)
                except ValueError:
                    rel_in_folder = Path(src.name)
                dst = out_dir / rel_in_folder
                pairs.append((src, dst))
    return pairs


def copy_file(src, dst):
    """Copy ``src`` to ``dst`` creating parent directories as needed.

    Uses :func:`shutil.copy2` so file metadata (mtime, permissions) is
    preserved.

    Parameters
    ----------
    src : pathlib.Path
        Source file to copy.
    dst : pathlib.Path
        Destination path. Parent directories are created if missing.

    Returns
    -------
    ok : bool
        ``True`` if the copy succeeded, ``False`` otherwise.
    message : str
        Human-readable status string suitable for logging.
    """
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True, f"Copied: {src} -> {dst}"
    except (OSError, shutil.Error) as exc:
        return False, f"Failed to copy {src} -> {dst}: {exc}"


def validate_appn_path(folder):
    """Validate a ``.graw``/``.gpro`` folder against the APPN structure.

    Wraps :func:`parse_APPN_dataset_path` with ``path_level="sub_tier"``
    and converts any unexpected exception into an invalid result rather
    than aborting the run. A ``.graw``/``.gpro`` folder is expected to
    sit at the ``sub_tier`` level
    (``.../<sensor>/<YYYYMMDD>/run_XX/<T0_raw|T1_proc>/<X.graw>``).

    Parameters
    ----------
    folder : pathlib.Path
        Source folder to validate.

    Returns
    -------
    dict
        Result dictionary with at least the following keys:

        - ``valid`` (bool): whether the path matches the APPN layout.
        - ``errors`` (list of str): human-readable error messages.
        - parsed metadata fields (``node``, ``project``,
          ``site_folder``, ``year``, ``sensor``, ``date``,
          ``run_folder``, ``run``, ``tier``, ``sub_tier``).
    """
    try:
        parsed = parse_APPN_dataset_path(folder, path_level="sub_tier")
    except Exception as exc:  # noqa: BLE001 - report any parser failure
        return {
            'valid': False,
            'errors': [f'parse_APPN_dataset_path raised {type(exc).__name__}: {exc}'],
        }
    return parsed


def _fmt_appn(value):
    """Format a parsed APPN value for inclusion in the CSV.

    Parameters
    ----------
    value : object
        Value from a :func:`parse_APPN_dataset_path` result. May be
        ``None``, a :class:`pandas.Timestamp`, or any object with a
        meaningful ``str()`` representation.

    Returns
    -------
    str
        Empty string for ``None``; ``YYYYMMDD`` for date-like values
        with a ``strftime`` method; ``str(value)`` otherwise.
    """
    if value is None:
        return ''
    # pandas Timestamp has isoformat / strftime; fall back to str.
    try:
        # pd.Timestamp
        return value.strftime('%Y%m%d')
    except AttributeError:
        return str(value)


def write_manifest(manifest_path, folders):
    """Write the manifest CSV mapping labels to source/output paths.

    Each row records identification fields, source and destination
    paths, the APPN-validation outcome and parsed metadata. See the
    module docstring for the full column list.

    Parameters
    ----------
    manifest_path : pathlib.Path
        Output CSV path. Parent directories are created if missing.
    folders : list of dict
        Folder records as produced by :func:`find_target_folders` and
        further annotated in :func:`main` (``number``, ``label``,
        ``out_dir``, ``appn``).

    Returns
    -------
    None
        Writes the manifest to disk as a side effect.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        'sensor', 'kind', 'number', 'label',
        'source_path', 'output_path',
        'appn_valid', 'appn_errors',
        'node', 'project', 'site_folder', 'year', 'sensor_folder',
        'date', 'run_folder', 'run', 'tier', 'sub_tier',
    ]
    with open(manifest_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for rec in folders:
            appn = rec.get('appn', {}) or {}
            errors = appn.get('errors') or []
            writer.writerow([
                rec['sensor'], rec['kind'], rec['number'], rec['label'],
                str(rec['source']), str(rec['out_dir']),
                bool(appn.get('valid')),
                ' | '.join(errors),
                appn.get('node') or '',
                appn.get('project') or '',
                appn.get('site_folder') or '',
                _fmt_appn(appn.get('year')),
                appn.get('sensor') or '',
                _fmt_appn(appn.get('date')),
                appn.get('run_folder') or '',
                _fmt_appn(appn.get('run')),
                appn.get('tier') or '',
                appn.get('sub_tier') or '',
            ])


if __name__ == '__main__':
    main()
