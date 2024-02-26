import os
import subprocess

from .get_args import get_args, Config
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

def create_registry(prog_config: Config) -> ProjectRegistry:
    config = dict()
    if prog_config.configuration is not None:
        config[CONFIGURATION] = prog_config.configuration.value
    if prog_config.platform is not None:
        config[PLATFORM] = prog_config.platform.value
    return ProjectRegistry(config)

def main():

    prog_config = get_args()
    registry = create_registry(prog_config)

    os.chdir(prog_config.repo)

    for line in find_projects(prog_config.root).stdout.splitlines():
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
                output = project.output()
                if output is not None:
                    print("  output:", output)
            case ProjectLoadDangling(backtrace) | ProjectLoadCycle(backtrace):
                print("Dangling")
                for project_id in reversed(backtrace):
                    print("  " + str(project_id))



if __name__ == "__main__":
    main()
