import os
import subprocess

from .get_args import get_args
from ..lib.project_registry import ProjectRegistry
from ..lib.id import SimpleProjectId
from ..lib.project import (
    Project,
    ProjectLoadResult,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadCycle
)
from ..lib import util


def run_find(*args, **kwargs):
    if "capture_output" not in kwargs:
        kwargs["capture_output"] = True
    if "check" not in kwargs:
        kwargs["check"] = True
    if "text" not in kwargs:
        kwargs["text"] = True
    return subprocess.run(["fd", *args], **kwargs)


def find_projects(repo):
    return run_find("\\.csproj$", str(repo))


def main():

    config = get_args()
    registry = ProjectRegistry()

    os.chdir(config.repo)
    for line in find_projects(config.root).stdout.splitlines():
        path = util.normalize_windows_path(line)
        name = path.stem
        project_id = SimpleProjectId(name, path)
        match registry.load(project_id):
            case ProjectLoadOk(project):
                pass
                #print("Complete")
                #print("  " + str(project.project_id))
            case ProjectLoadDangling(backtrace) | ProjectLoadCycle(backtrace):
                print("Dangling")
                for project_id in reversed(backtrace):
                    print("  " + str(project_id))


if __name__ == "__main__":
    main()
