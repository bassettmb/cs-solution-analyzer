
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

from ..lib import util


@dataclass
class Config:
    repo: Path
    root: Path


def get_args() -> Config:

    parser = ArgumentParser(
        prog="repo-dependency-analyzer",
        description="Multi-project dependency analysis."
    )
    parser.add_argument(
        "-r", "--root",
        dest="root",
        default=".",
        help="subtree of the repository in which to search"
    )
    parser.add_argument(
        "repo",
        metavar="REPOSITORY",
        help="repository in which to search"
    )

    args = parser.parse_args()
    repo = util.normalize_windows_path(args.repo)
    root = util.normalize_windows_path(args.root)

    return Config(repo, root)
