import os
import subprocess

from .get_args import get_args, Config
from ..lib.id import ProjectId
from ..lib.multimap import MultiMap
from ..lib.project import (
    CONFIGURATION, PLATFORM,
    Project,
    ProjectLoadResult,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadIncompatible, ProjectLoadCycle,
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

    def dump_backtrace(backtrace: list[ProjectId], prefix: str = ""):
        for project_id in reversed(backtrace):
            print(prefix + str(project_id))


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
            case ProjectLoadDangling(backtrace):
                print("Dangling")
                dump_backtrace(backtrace, "  ")
            case ProjectLoadIncompatible(backtrace):
                print("Incompatible (unrecognized csproj format)")
                dump_backtrace(backtrace, "  ")
            case ProjectLoadCycle(backtrace):
                print("Project contains Import cycle")
                dump_backtrace(backtrace, "  ")

    # def complete(self) -> MapView[ProjectId, Project]:

    # TODO: rip the guts out of solution.py
    # mix the below in with the guts
    # incorporate into a new class the solution will compose with
    complete = registry.complete()

    output_by_id = dict()
    id_by_output = dict()
    duplicated_outputs = MultiMap()

    for id, project in complete.items():
        if id in output_by_id:
            raise RuntimeError("same id for multiple project??")
        output = project.output()
        if output is None:
            from sys import stderr
            print(f"Warning: could not guess output for project {id}", file=stderr)
        elif output in id_by_output:
            duplicated_outputs.add(output, id)
            duplicated_outputs.add(output, id_by_output[output])
        else:
            output_by_id[id] = output
            id_by_output[output] = id

    if len(duplicated_outputs) > 0:
        print("Distinct projects producing the same output:")
        for output, ids in duplicated_outputs.items():
            print("  ", str(output))
            for id in ids:
                print("    ", str(id))



if __name__ == "__main__":
    main()
