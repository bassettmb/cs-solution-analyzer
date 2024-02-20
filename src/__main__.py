import os
import subprocess

from .get_args import get_args
from .solution import Solution


def run_find(*args, **kwargs):
    if "capture_output" not in kwargs:
        kwargs["capture_output"] = True
    if "check" not in kwargs:
        kwargs["check"] = True
    if "text" not in kwargs:
        kwargs["text"] = True
    return subprocess.run(["fd", *args], **kwargs)


def find_solutions(repo):
    return run_find("\\.sln$", str(repo))


# TODO:
#   project <Import>s
#   set up scans for duplicate files -- shasum it
#   extract output assemblies -- we want to know what makes what
#   do something interesting with globs & substitutions
#     this means what? factory method? path -> many paths


def main():

    config = get_args()

    os.chdir(config.repo)
    for line in find_solutions(config.root).stdout.splitlines():

        solution = Solution(line)
        indent = "    "
        acyclic, project_deps = solution.topsort()

        if solution.is_broken or not acyclic:
            print(solution.path)
            if not acyclic:
                print(indent + "dependency cycle:")
                for project_dep in project_deps:
                    print(indent * 2 + str(project_dep.path))
            if solution.has_duplicated_guids:
                print(indent + "duplicated guids:")
                for guid, project_ids in solution.duplicated_guids().items():
                    print(indent * 2 + str(guid))
                    parent_map = solution.project_parents()
                    for project_id in project_ids:
                        print(indent * 3 + str(project_id))
                        if project_id in parent_map:
                            for parent in parent_map[project_id]:
                                print(indent * 4, str(parent.path))
                        else:
                            print(indent * 4, "<root>")
            if solution.has_undeclared_projects:
                print(indent + "undeclared projects:")
                for project, project_ids in solution.undeclared_projects():
                    print(indent * 2 + str(project.path))
                    for project_id in project_ids:
                        print(indent * 3 + str(project_id.path))
            if solution.has_dangling_projects:
                print(indent + "dangling projects:")
                for project_id in solution.dangling_projects():
                    print(indent * 2 + str(project_id.path))
            if solution.has_dangling_assemblies:
                print(indent + "dangling assemblies:")
                assemblies = solution.dangling_assemblies()
                for project_id, assembly_ids in assemblies.items():
                    print(indent * 2 + str(project_id.path))
                    for assembly_id in assembly_ids:
                        print(indent * 3 + str(assembly_id.path))
            if solution.has_dangling_sources:
                print(indent + "dangling_sources:")
                sources = solution.dangling_sources()
                for (project_id, source_ids) in sources.items():
                    print(indent * 2 + str(project_id.path))
                    for source_id in source_ids:
                        print(indent * 3 + str(source_id.path))


if __name__ == "__main__":
    main()
