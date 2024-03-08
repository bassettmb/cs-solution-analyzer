
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

from ..lib import util


@dataclass
class Config:
    solution: Path


def get_args() -> Config:

    parser = ArgumentParser(
        prog="find_projects",
        description="Find all projects belonging to a VS solution."
    )
    parser.add_argument(
        "solution",
        metavar="SOLUTION",
        help="solution to scan for projects"
    )

    args = parser.parse_args()
    solution = util.normalize_windows_path(args.solution)

    return Config(solution)
