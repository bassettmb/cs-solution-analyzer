import os
from pathlib import Path, PureWindowsPath


def normalize_windows_path(path: str | Path) -> Path:
    return Path(os.path.normpath(Path(*PureWindowsPath(path).parts)))


def normalize_windows_relpath(context: Path, path: str | Path) -> Path:
    rel_path = PureWindowsPath(path)
    denorm_path = context.joinpath(rel_path)
    return Path(os.path.normpath(denorm_path))
