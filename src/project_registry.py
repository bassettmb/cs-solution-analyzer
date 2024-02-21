
from .data_view import MapView, SetView

from .id import ProjectId
from .project import (
    Project,
    ProjectLoadResult,
    ProjectLoadComplete, ProjectLoadDangling, ProjectLoadCycle
)


# class ProjectLoadComplete:
#     project: "Project"
# class ProjectLoadDangling:
#     backtrace: list[ProjectId]
# class ProjectLoadCycle:
#    backtrace: list[ProjectId]
# ProjectLoadResult = Union

class ProjectRegistry:

    _project_complete: dict[ProjectId, Project]
    _project_dangling: set[ProjectId]
    _project_loading: set[ProjectId]

    def __init__(self):
        self._project_complete = dict()
        self._project_dangling = set()
        self._project_loading = set()

    def load(self, project_id: ProjectId) -> ProjectLoadResult:

        if project_id in self._project_complete:
            return ProjectLoadComplete(self._project_complete[project_id])
        if project_id in self._project_dangling:
            return ProjectLoadDangling([project_id])
        if project_id in self._project_loading:
            return ProjectLoadCycle([project_id])


        try:
            result = Project.load(self, project_id)
        finally:
            self._project_loading.remove(project_id)

        match result:
            case ProjectLoadComplete(project):
                self._project_complete[project_id] = project
                return ProjectLoadComplete(project)
            case ProjectLoadDangling(backtrace):
                self._project_dangling.add(project_id)
                backtrace.append(project_id)
                return ProjectLoadDangling(backtrace)
            case ProjectLoadCycle(backtrace):
                backtrace.append(project_id)
                return ProjectLoadCycle(backtrace)

    def complete(self) -> MapView[ProjectId, Project]:
        return MapView(self._project_complete)

    def dangling(self) -> SetView[ProjectId]:
        return SetView(self._project_dangling)
