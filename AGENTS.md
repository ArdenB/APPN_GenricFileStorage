# AGENTS.md — Coding rules for AI assistants

> Machine-readable. Read this first.
> Audience: LLM coding agents (Copilot, Claude, Cursor, Aider, etc.).
> Scope: Python data-science / scientific-analysis scripts in this repo.

---

## 1. Hard rules (must follow)

- **R1** — All executable code lives inside functions. **No top-level work** other than imports, `__title__`/`__author__` metadata, and the `if __name__ == "__main__":` block.
- **R2** — **No global variables.** Pass everything via function arguments. The only allowed module-level names are: imports, dunder metadata, and constants in `UPPER_SNAKE_CASE` that are truly immutable.
- **R3** — `main()` is defined **at the top of the file**, immediately after imports. It reads like pseudocode; complex logic lives in helper functions below.
- **R4** — All functions use **NumPy-style docstrings** with `Parameters`, `Returns`, and (when relevant) `Raises` / `Notes` sections. Include type hints on signatures.
- **R5** — Scripts run from the **git repo root**. The git root is resolved with `gitpython` and added to `sys.path` **at module top** (before any `functions.*` imports), and the `__main__` block `chdir`s into it before calling `main()`. All paths in code are relative to the repo root or come from CLI args.
- **R6** — Use `argparse` for any user-tunable input. No hard-coded paths inside `main()`.
- **R7** — **No Jupyter notebooks** for analysis. Notebooks are for teaching/exploration only.
- **R8** — Prefer existing helpers in `functions.corefunctions` (e.g. `storagefinder`, `pymkdir`, `writemetadata`, `gitmetadata`) over re-implementing them.
- **R9** — Don't add `try/except` around code unless a *specific* failure mode is being handled. No bare `except:`.

## 2. Soft preferences

- **P1** — Section banners use `# ========== Title ==========` for major sections and `# +++++ subnote +++++` for inline subsections. Function separators use a line of `=` (~80 chars).
- **P2** — Keep `main()` short. Each step is one call to a helper.
- **P3** — Use `pathlib.Path` over `os.path` strings.
- **P4** — Use `tqdm` for any loop over files/large iterables.
- **P5** — Use `warnings.warn(...)` (imported as `warn`) for recoverable issues; raise for unrecoverable ones.
- **P6** — Plotting: `seaborn` for stats plots, `matplotlib` for fine-tuning. Set style/rcParams once inside the plot function, not at module level.
- **P7** — File-type defaults: `parquet` for tabular data on disk; `csv` only for human-edited / small metadata files.
- **P8** — Print a one-line progress message at the start of each major step (`print(f"Loading {fpath} ...")`).
- **P9** — Avoid copying a function between scripts. If two scripts need it, prefer moving it into `functions/` and importing it.
- **P10** - Use `tqdm` when using for loops instead of print statements.

## 3. Forbidden patterns

- ❌ Mutable module-level state (`results = []` at top level, then appended inside functions).
- ❌ Importing `*`.
- ❌ `os.chdir` inside `main()` or helper functions (only allowed in `__main__`).
- ❌ Hard-coded absolute paths (`/mnt/d/...`) in committed code. Use args / `storagefinder`.
- ❌ Re-implementing things already in `functions/`.
- ❌ Silent `except: pass`.
- ❌ Adding new top-level scripts that don't follow the template in §4.

## 4. Canonical script template

Every new script in `code/` MUST match this skeleton:

```python
"""One-line summary.

Longer description of what the script does, its inputs, and its outputs.

Command-line Arguments
----------------------
--foo : str
    Description.
"""

# ==============================================================================

__title__ = "Short title"
__author__ = "Arden Burrell"
__version__ = "v1.0(DD.MM.YYYY)"
__email__ = "arden.burrell@sydney.edu.au"

# ==============================================================================
# ========== Import core packages ==========
import os
import sys
import argparse
import pathlib
from typing import Optional, List

# ========== Import other packages ==========
import git
from git import exc as git_exc
import numpy as np
import pandas as pd
from tqdm import tqdm
import warnings as warn

import matplotlib.pyplot as plt
import seaborn as sns

# ========== Resolve git root (must happen before importing functions.*) ==========
try:
    _git_root = git.Repo(os.getcwd(), search_parent_directories=True
                         ).git.rev_parse("--show-toplevel")
except git_exc.InvalidGitRepositoryError as err:
    raise git_exc.InvalidGitRepositoryError(
        f"Script must be run from inside a git repo (cwd={os.getcwd()})."
    ) from err
if _git_root not in sys.path:
    sys.path.insert(0, _git_root)

# ========== Import custom packages ==========
import Code.functions.corefunctions as cf
# import Code.functions.spectralfunction as sf

# ==================================================================================
def main(args: argparse.Namespace) -> None:
    """Top-level orchestration. Reads like pseudocode.

    Parameters
    ----------
    args : argparse.Namespace
        Parsed CLI arguments.

    Returns
    -------
    None
    """
    # ========== Step 1 ==========
    df = load_data(pathlib.Path(args.input))
    # ========== Step 2 ==========
    df = clean_data(df)
    # ========== Step 3 ==========
    make_plots(df)


# ==================================================================================
def load_data(path: pathlib.Path) -> pd.DataFrame:
    """Load a parquet/csv file.

    Parameters
    ----------
    path : pathlib.Path
        Input file.

    Returns
    -------
    pd.DataFrame
    """
    ...


# ==================================================================================
if __name__ == "__main__":
    # ========== chdir to git root (resolved at module top) ==========
    os.chdir(_git_root)

    # ========== Parse args ==========
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--input", type=str, required=True, help="...")
    args = parser.parse_args()

    main(args)
```

## 5. Quick checklist for the agent (run before returning code)

- [ ] `main()` is the first function definition.
- [ ] No globals; no top-level work outside `__main__`.
- [ ] Every function has a NumPy-style docstring + type hints.
- [ ] Section banners use the `# ========== ... ==========` style.
- [ ] CLI args used instead of hard-coded paths.
- [ ] Git root is added to `sys.path` at module top (before `functions.*` imports); `__main__` `chdir`s to it.
- [ ] Reused logic comes from `functions/` (not copy-pasted).
- [ ] No new notebooks for analysis.

## 6. Reference files

- Shared helpers: [`functions/corefunctions/__init__.py`](functions/corefunctions/__init__.py)
