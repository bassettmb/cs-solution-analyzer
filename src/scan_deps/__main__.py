import os
import subprocess

from typing import Optional

from .get_args import get_args, Config
from ..lib.id import ProjectId
from ..lib.multimap import MultiMap
from ..lib.project import (
    CONFIGURATION, PLATFORM,
    Project,
    ProjectLoadResult,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadIncompatible, ProjectLoadCycle,
    ProjectSet
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

def create_project_set(prog_config: Config) -> ProjectSet:
    config = dict()
    if prog_config.configuration is not None:
        config[CONFIGURATION] = prog_config.configuration.value
    if prog_config.platform is not None:
        config[PLATFORM] = prog_config.platform.value
    return ProjectSet(config.items())

def compute_build_order(project_set: ProjectSet):

    projects = project_set.complete()
    projects_by_output = project_set.projects_by_output()
    projects_by_output_name = MultiMap()
    for assembly_id, project_id in projects_by_output.items():
        projects_by_output_name.add(assembly_id.name, project_id)

    build_order = []
    complete = set()
    scanning = set()

    def mark_complete(project_id):
        complete.add(project_id)
        build_order.append(project_id)

    def visit(project_id: ProjectId) -> Optional[list[ProjectId]]:

        if project_id in complete:
            return None  # already done
        if project_id in scanning:
            return [project_id]  # dependency cycle

        # we'll pretend projects we couldn't load are complete
        if project_id in projects:
            scanning.add(project_id)
            try:
                project = projects[project_id]

                # recurse on project refs
                for subproject_id in project.project_refs():
                    result = visit(subproject_id)
                    if result is not None:  # dependency cycle
                        result.append(project_id)
                        return result

                # recurse on assembly refs
                for assembly_id in project.assembly_refs():
                    # look for a project producing an assembly with the required name
                    if assembly_id.name in projects_by_output_name:
                        # .. maybe we can get away without having to choose
                        # we cannot. just pick one for now I guess.
                        subproject_ids = projects_by_output_name[assembly_id.name]
                        subproject_id = next(iter(subproject_ids))
                        result = visit(subproject_id)
                        if result is not None:  # dependency cycle
                            result.append(project_id)
                            return result

            finally:
                scanning.remove(project_id)

        mark_complete(project_id)
        return None

    for project_id in projects:
        result = visit(project_id)
        if result is not None:
            raise RuntimeError(
                "\n  ".join(["Dependency cycle", *map(str, result)])
            )

    result.reverse()
    return result

def main():

    prog_config = get_args()
    pset = create_project_set(prog_config)

    os.chdir(prog_config.repo)

    for line in find_projects(prog_config.root).stdout.splitlines():
        path = util.normalize_windows_path(line)
        name = path.stem
        project_id = ProjectId(name, path)
        pset.add(project_id)

    projects_without_output = pset.projects_without_output()
    if len(projects_without_output) > 0:
        print("Projects without (guessable) output:")
        for id in projects_without_output:
            print("  ", str(id.path))

    duplicate_outputs = pset.duplicate_outputs()
    if len(duplicate_outputs) > 0:
        print("Distinct projects producing the same output:")
        for output, ids in duplicate_outputs.items():
            print("  ", str(output.path))
            for id in ids:
                print("    ", str(id.path))

    # We want to be able to do what ...

    # accept a function restricting assemblies add as dependencies
    # accept a set of given assemblies
    # accept a set of project_ids
    # compute a build order for projects

    # alternatively, just work with what we have...

    # Ok, so now we want to join references with outputs to compute dependencies

    complete = pset.complete()
    projects_by_output = pset.projects_by_output()
    projects_by_output_name = MultiMap()
    for assembly_id, project_id in projects_by_output.items():
        projects_by_output_name.add(assembly_id.name, project_id)

    for assembly_name, project_ids in projects_by_output_name.items():
        if len(project_ids) > 1:
            print(f"multiple producers for assembly {assembly_name}:")
            for project_id in project_ids:
                print(f"  {project_id.path}")

    missing_assembly_refs = MultiMap()
    for project_id, project in complete.items():
        for assembly_id in project.assembly_refs():
            assembly_name = assembly_id.name
            if (
                    assembly_name.startswith() and
                    assembly_name not in projects_by_output_name
            ):
                missing_assembly_refs.add(assembly_id, project_id)

    if len(missing_assembly_refs) > 0:
        print("unsatisfied assembly deps:")
        for assembly_id, project_ids in missing_assembly_refs.items():
            print(f"  assembly: {assembly_id}")
            print("    wanted by:")
            for project_id in project_ids:
                print(f"      {project_id}")

    print("\n  ".join(["Build order:", *map(str, compute_build_order(pset))]))

    # for project_id, project in complete.items():
    #     for assembly_id in project.assembly_refs():
    #         if assembly_id.name in projects_by_output_name:
    #             print(f"assembly: {assembly_id.name}")
    #             print(f"  consumer: {project_id}")
    #             print("  producers:")
    #             for producer in projects_by_output_name[assembly_id.name]:
    #                 print(f"    {producer}")




if __name__ == "__main__":
    main()
