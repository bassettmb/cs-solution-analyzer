from collections.abc import KeysView
from ..id import AssemblyId, ProjectId, SourceId
from ..data_view import MapView, SetView
from ..multimap import MultiMap, MultiMapView
from .project import (
    Project,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadIncompatible, ProjectLoadCycle,
)
from .registry import ProjectRegistry

class ProjectSet:

    _registry: ProjectRegistry

    _project_parents: MultiMap[ProjectId, ProjectId]
    _project_outputs: dict[ProjectId, AssemblyId]

    _project_cyclic: set[ProjectId]
    _assembly_dangling: MultiMap[ProjectId, AssemblyId]
    _source_dangling: MultiMap[ProjectId, SourceId]

    _output_by_project: dict[ProjectId, AssemblyId]
    _project_by_output: dict[AssemblyId, ProjectId]
    _projects_sans_output: set[ProjectId]
    _duplicate_outputs: MultiMap[AssemblyId, ProjectId]

    def __init__(self):

        self._registry = ProjectRegistry()

        self._project_parents = MultiMap()
        self._project_outputs = dict()

        self._project_cyclic = set()
        self._assembly_dangling = MultiMap()
        self._source_dangling = MultiMap()

        self._outputs_by_project = dict()
        self._projects_by_output = dict()
        self._projects_sans_output = set()
        self._duplicate_outputs = MultiMap()

    def add(self, project_id: ProjectId):
        project_ids = [project_id]
        while len(project_ids) > 0:
            project_id = project_ids.pop()
            if (
                    project_id in self._registry.complete() or
                    project_id in self._registry.dangling() or
                    project_id in self._registry.incompatible() or
                    project_id in self._project_cyclic
            ):
                continue

            match self._registry.load(project_id):
                case ProjectLoadOk(project):
                    for subproject_id in project.project_refs():
                        self._project_parents.add(subproject_id, project.project_id)
                        project_ids.append(subproject_id)
                    for assembly_id in project.assembly_refs():
                        assembly_path = assembly_id.path
                        if (
                                assembly_path is not None and
                                not assembly_path.exists()
                        ):
                            self._assembly_dangling.add(project_id, assembly_id)
                    output = project.output()
                    if output is None:
                        self._projects_sans_output.add(project_id)
                    elif output in self._duplicate_outputs:
                        self._duplicate_outputs.add(output, project_id)
                    elif output in self._projects_by_output:
                        dup_id = self._projects_by_output.pop(output)
                        del self._outputs_by_project[dup_id]
                        self._duplicate_outputs.add(output, project_id)
                        self._duplicate_outputs.add(output, dup_id)
                    else:
                        self._projects_by_output[output] = project_id
                        self._outputs_by_project[project_id] = output
                case ProjectLoadDangling(_) | ProjectLoadIncompatible(_):
                    pass
                case ProjectLoadCycle(_):
                    self._project_cyclic.add(project_id)

    def complete(self) -> MapView[ProjectId, Project]:
        return self._registry.complete()

    def incompatible(self) -> SetView[ProjectId]:
        return self._registry.incompatible()

    def cyclic(self) -> SetView[ProjectId]:
        return SetView(self._project_cyclic)

    def parents(self) -> MultiMapView[ProjectId, ProjectId]:
        return MultiMapView(self._project_parents)

    def dangling_projects(self) -> SetView[ProjectId]:
        return self._registry.dangling()

    def dangling_assemblies(
            self
    ) -> MultiMapView[ProjectId, AssemblyId]:
        return MultiMapView(self._assembly_dangling)

    def dangling_sources(
            self
    ) -> MultiMapView[ProjectId, SourceId]:
        return MultiMapView(self._source_dangling)

    def outputs(self) -> KeysView[AssemblyId]:
        return self._project_by_output.keys()

    def projects_by_output(self) -> MapView[AssemblyId, ProjectId]:
        return MapView(self._project_by_output)

    def outputs_by_project(self) -> MapView[ProjectId, AssemblyId]:
        return MapView(self._output_by_project)

    def duplicate_outputs(self) -> MultiMapView[AssemblyId, ProjectId]:
        return MultiMapView(self._duplicate_outputs)
