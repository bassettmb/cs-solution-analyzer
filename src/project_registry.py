from typing import Iterable, assert_never

from .var_env import VarEnv
from .project import (
    Project,
    ProjectEnv, ProjectProperty, ProjectString,
    ProjectLoadComplete, ProjectLoadDangling, ProjectLoadCycle,
    ProjectLoadResult
)
from .id import ProjectId


class ProjectRegistry:

    _env: ProjectEnv
    _complete: dict[ProjectId, Project]
    _dangling: set[ProjectId]
    _loading: set[ProjectId]

    def __init__(
            self,
            bindings: Iterable[tuple[ProjectProperty, ProjectString]]
    ):
        self._env = VarEnv(bindings)
        self._complete = dict()
        self._dangling = set()
        self._loading = set()

    def load(self, project_id: ProjectId) -> ProjectLoadResult:
        if project_id in self._complete:
            return ProjectLoadComplete(self._complete[project_id])
        if project_id in self._dangling:
            return ProjectLoadDangling(project_id)
        if project_id in self._loading:
            return ProjectLoadCycle([project_id])
        self._loading.add(project_id)
        try:
            result = Project.load(self, project_id)
        finally:
            self._loading.remove(project_id)
        match result:
            case ProjectLoadComplete(project):
                self._complete[project_id] = project
                return ProjectLoadComplete(project)
            case ProjectLoadDangling(backtrace):
                self._dangling.add(project_id)
                backtrace.append(project_id)
                return ProjectLoadDangling(backtrace)
            case ProjectLoadCycle(backtrace):
                backtrace.append(project_id)
                return ProjectLoadCycle(backtrace)
            case result:
                assert_never(result)
