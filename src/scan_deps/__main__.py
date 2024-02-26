import os
import subprocess

from .get_args import get_args
from ..lib.id import ProjectId
from ..lib.project import (
    Project,
    ProjectLoadResult,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadCycle,
    ProjectRegistry
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

    count = 10

    os.chdir(config.repo)
    for line in find_projects(config.root).stdout.splitlines():
        path = util.normalize_windows_path(line)
        name = path.stem
        project_id = ProjectId(name, path)
        match registry.load(project_id):
            case ProjectLoadOk(project):
                print(project_id)
                print("  project refs")
                for subproject_id in project.project_refs():
                    print("    " + str(subproject_id))
                print("  assembly refs")
                for assembly_id in project.assembly_refs():
                    print("    " + str(assembly_id))
                print("  properties")
                for key, value in project.properties().items():
                    print(f"    {key}: {value}")
            case ProjectLoadDangling(backtrace) | ProjectLoadCycle(backtrace):
                print("Dangling")
                for project_id in reversed(backtrace):
                    print("  " + str(project_id))
        break
        count -= 1
        if count <= 0:
            break



if __name__ == "__main__":
    main()
