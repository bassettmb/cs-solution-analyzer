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


# class ProjectRegistry:

#     _env: ProjectEnv
#     _complete: dict[ProjectId, Project]
#     _dangling: set(ProjectId)
#     _loading: set(ProjectId)

#     def __init__(
#             self,
#             bindings: Iterable[tuple[ProjectProperty, ProjectString]]
#     ):
#         self._env = ProjectEnv(VarEnv(bindings))
#         self._complete = dict()
#         self._dangling = set()
#         self._loading = set()

#     def _load_recursive(self, project_id: ProjectId) -> ProjectLoadResult:
#         if project_id in self._complete:
#             return ProjectLoadOk(self._complete[project_id])
#         if project_id in self._dangling:
#             return ProjectLoadDangling(project_id)
#         if project_id in self._loading:
#             return ProjectLoadCycle([project_id])
#         self._loading.add(project_id)
#         load_result = Project.load(self, project_id)


#     def load(self, project_id: ProjectId):
#         for guid in self._project_roots:
#             stack.append(self._project_roots[guid])
#         while len(stack) > 0:
#             project_id = stack.pop()
#             guid = project_id.guid
#             assert (
#                 (project_id.guid not in self._project_registry) or
#                 self._project_registry[project_id.guid].project_id == project_id
#             )
#             if not (guid in self._project_registry or
#                     guid in self._project_dangling):
#                 project = Project.load(project_id)
#                 if project is None:
#                     self._project_dangling[guid] = project_id
#                 else:
#                     self._project_registry[guid] = Project(project_id)
#                     for project_id in project.project_refs():
#                         stack.append(project_id)


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
                for (project_id, assembly_ids) in solution.dangling_assemblies():
                    print(indent * 2 + str(project_id.path))
                    for assembly_id in assembly_ids:
                        print(indent * 3 + str(assembly_id.path))
            if solution.has_dangling_sources:
                print(indent + "dangling_sources:")
                for (project_id, source_ids) in solution.dangling_sources():
                    print(indent * 2 + str(project_id.path))
                    for source_id in source_ids:
                        print(indent * 3 + str(source_id.path))


if __name__ == "__main__":
    main()
