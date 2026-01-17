"""Shared CLI utilities for fix_struct_asym commands."""

from __future__ import annotations

import os

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

# Default number of workers: use half of CPU cores, minimum 1, maximum 8
DEFAULT_WORKERS = min(8, max(1, (os.cpu_count() or 4) // 2))

# Rich consoles for output
console = Console()
err_console = Console(stderr=True)


def create_progress() -> Progress:
    """Create a standardized rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=err_console,
    )
