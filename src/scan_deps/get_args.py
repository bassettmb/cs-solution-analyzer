from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..lib import util
from ..lib.project import Configuration, Platform


@dataclass
class Config:
    repo: Path
    root: Path
    configuration: Optional[Configuration]
    platform: Optional[Platform]


def get_args() -> Config:

    parser = ArgumentParser(
        prog="project-dependency-analyzer",
        description="Multi-project dependency analysis."
    )
    parser.add_argument(
        "-r", "--root",
        dest="root",
        default=".",
        help="subtree of the repository in which to search"
    )
    parser.add_argument(
        "-c", "--configuration",
        dest="configuration",
        choices=Configuration.values(),
        help="value for the 'Configuration' property to use"
    )
    parser.add_argument(
        "-p", "--platform",
        dest="platform",
        choices=Platform.values(),
        help="value to use for the 'Platform'"
    )
    parser.add_argument(
        "repo",
        metavar="REPOSITORY",
        help="repository in which to search"
    )

    args = parser.parse_args()

    repo = util.normalize_windows_path(args.repo)
    root = util.normalize_windows_path(args.root)

    configuration = args.configuration
    if configuration is not None:
        configuration = Configuration.from_string(configuration)

    platform = args.platform
    if platform is not None:
        platform = Platform.from_string(platform)

    return Config(repo, root, configuration, platform)
