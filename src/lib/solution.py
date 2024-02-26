import enum
import re

from enum import Enum
from collections.abc import (
    Iterable, Iterator,
    MutableMapping, MutableSet,
    Mapping, Set,
    ValuesView
)
from pathlib import Path
from typing import Generic, Optional, TypeVar

from . import util
from .id import AssemblyId, Guid, ProjectId, ProjectId, SourceId
from .data_view import SetView
from .multimap import (
    MultiMap, MultiMapView, MultiMapItemsView, MultiMapValuesView
)
from .project import (
    Project,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadIncompatible, ProjectLoadCycle,
    ProjectLoadResult,
    ProjectRegistry
)


def _build_parse_project_regexp():
    prefix = r'.*Project[^=]*=\s*'
    name = r'"(?P<name>[^"]*)"\s*'
    path = r'"(?P<path>[^"]*\.csproj)"\s*'
    guid = r'"\{(?P<guid>[^\}]*)\}"\s*'
    sep = r',\s*'
    return re.compile(''.join([prefix, name, sep, path, sep, guid]))


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
                        self._duplicate_output.add(output, project_id)
                        self._duplicate_output.add(output, dup_id)
                    else:
                        self._projects_by_output[output] = project_id
                        self._outputs_by_project[project_id] = output
                case ProjectLoadDangling(_) | ProjectLoadIncompatible(_):
                    pass
                case ProjectLoadCycle(_):
                    self._project_cyclic.add(project_id)

    def projects(self) -> ValuesView[Project]:
        return self._registry.complete().values()

    def dangling_projects(self) -> SetView[ProjectId]:
        return self._registry.dangling()

    def incompatible_projects(self) -> SetView[ProjectId]:
        return self._registry.incompatible()

    def cyclic_projects(self) -> SetView[ProjectId]:
        return SetView(self._project_cyclic)

    def dangling_assemblies(
            self
    ) -> MultiMapView[ProjectId, AssemblyId]:
        return MultiMapView(self._assembly_dangling)

    def dangling_sources(
            self
    ) -> MultiMapView[ProjectId, SourceId]:
        return MultiMapView(self._source_dangling)

    def outputs(self) -> KeysView[AssemblyId]:
        return self._output_by_project.keys()

    def projects_by_output(self) -> MapView[ProjectId, AssemblyId]:
        return MapView(self._project_by_output)

    def outputs_by_project(self) -> MapView[AssemblyId, ProjectId]:
        return MapView(self._output_by_project)

    def duplicate_outputs(self) -> MultiMap[AssemblyId, ProjectId]:
        return MultiViewMap(self._duplicate_outputs)


class Solution:

    # TODO: track the source of the broken stuff

    _path: Path
    _registry: ProjectRegistry

    _project_guids: MultiMap[ProjectId, Guid]
    _project_roots: set[ProjectId]

    _project_cyclic: set[ProjectId]

    _project_parents: MultiMap[ProjectId, ProjectId]
    _project_undeclared: MultiMap[ProjectId, ProjectId]
    _assembly_dangling: MultiMap[ProjectId, AssemblyId]
    _source_dangling: MultiMap[ProjectId, SourceId]
    _duplicated_guids: MultiMap[Guid, ProjectId]

    _PARSE_PROJECT_REGEXP = _build_parse_project_regexp()

    def __init__(self, path: str | Path):

        self._path = util.normalize_windows_path(path)
        self._registry = ProjectRegistry()

        self._project_guids = MultiMap()
        self._project_roots = set()

        self._project_cyclic = set()

        self._project_parents = MultiMap()
        self._project_undeclared = MultiMap()
        self._assembly_dangling = MultiMap()
        self._source_dangling = MultiMap()
        self._duplicated_guids = MultiMap()

        self._load()

    def _parse_project(self, line) -> Optional[tuple[Guid, ProjectId]]:

        match = self._PARSE_PROJECT_REGEXP.match(line)
        if match is None:
            return None
        name = match.group("name")
        path = match.group("path")
        guid = match.group("guid")

        repo_path = util.normalize_windows_relpath(self.path.parent, path)

        return (Guid(guid), ProjectId(name, repo_path))

    def _load_projects(self):
        stack = list(self._project_roots)
        while len(stack) > 0:
            project_id = stack.pop()
            if not (project_id in self._registry.complete() or
                    project_id in self._registry.dangling() or
                    project_id in self._registry.incompatible() or
                    project_id in self._project_cyclic):
                match self._registry.load(project_id):
                    case ProjectLoadOk(project):
                        for project_id in project.project_refs():
                            self._project_parents.add(project_id, project.project_id)
                            stack.append(project_id)
                    case ProjectLoadDangling(_) | ProjectLoadIncompatible(_):
                        pass
                    case ProjectLoadCycle(_):
                        self._project_cyclic.add(project_id)

    def _load_roots(self):
        with open(self._path, "r") as file:
            for line in file.readlines():
                result = self._parse_project(line)
                if result is not None:
                    guid, project_id = result
                    self._project_guids.add(project_id, guid)
                    self._project_roots.add(project_id)

    def topsort(self) -> tuple[bool, list[ProjectId]]:

        class Mark(Enum):
            WHITE = 0
            GREY = enum.auto()
            BLACK = enum.auto()

        marks: dict[ProjectId, Mark] = dict()
        output = []

        complete = self._registry.complete()
        dangling = self._registry.dangling()
        incompatible = self._registry.incompatible()

        def visit(project_id: ProjectId) -> Optional[list[ProjectId]]:
            match marks.get(project_id, Mark.WHITE):
                case Mark.GREY:
                    return [project_id]
                case Mark.BLACK:
                    return None
            if project_id in dangling or project_id in incompatible:
                marks[project_id] = Mark.BLACK
                output.append(project_id)
                return None
            marks[project_id] = Mark.GREY
            project = complete[project_id]
            for subproject_id in project.project_refs():
                result = visit(subproject_id)
                if result is not None:
                    result.append(project_id)
                    return result
            marks[project_id] = Mark.BLACK
            output.append(project_id)
            return None

        for root_id in self._project_roots:
            result = visit(root_id)
            if result is not None:
                result.append(root_id)
                result.reverse()
                return (False, result)

        output.reverse()
        return (True, output)

    def _scan_projects(self) -> None:
        guid_map: dict[Guid, ProjectId] = dict()
        for project_id, project in self._registry.complete().items():
            for (subproject_id, guids) in project.project_ref_guids().items():
                if subproject_id not in self._project_roots:
                    self._project_undeclared.add(project_id, subproject_id)
                for guid in guids:
                    if guid in guid_map:
                        other_id = guid_map[guid]
                        if other_id != subproject_id:
                            self._duplicated_guids.add(guid, other_id)
                            self._duplicated_guids.add(guid, subproject_id)
                    else:
                        guid_map[guid] = subproject_id
            for assembly in project.assembly_refs():
                assembly_path = assembly.path
                if assembly_path is not None and not assembly_path.exists():
                    self._assembly_dangling.add(project_id, assembly)
            for source in project.source_refs():
                if not source.path.exists():
                    self._source_dangling.add(project_id, source)

    def _load(self):
        self._load_roots()
        self._load_projects()
        self._scan_projects()

    @property
    def path(self):
        return self._path

    def project_roots(self) -> SetView[ProjectId]:
        return SetView(self._project_roots)

    def project_parents(self) -> MultiMapView[ProjectId, ProjectId]:
        return MultiMapView(self._project_parents)

    def projects(self) -> ValuesView[Project]:
        return self._registry.complete().values()

    @property
    def is_broken(self) -> bool:
        return (
            self.has_duplicated_guids or
            self.has_undeclared_projects or
            self.has_dangling_projects or
            self.has_dangling_assemblies or
            self.has_dangling_sources or
            self.has_incompatible_projects or
            self.has_cyclic_projects
        )

    @property
    def has_duplicated_guids(self) -> bool:
       return len(self._duplicated_guids) > 0

    @property
    def has_undeclared_projects(self) -> bool:
        return len(self._project_undeclared) > 0

    @property
    def has_dangling_projects(self) -> bool:
        return len(self._registry.dangling()) > 0

    @property
    def has_dangling_assemblies(self) -> bool:
        return len(self._assembly_dangling) > 0

    @property
    def has_dangling_sources(self) -> bool:
        return len(self._source_dangling) > 0

    @property
    def has_incompatible_projects(self) -> bool:
        return len(self._registry.incompatible()) > 0

    @property
    def has_cyclic_projects(self) -> bool:
        return len(self._project_cyclic) > 0

    def duplicated_guids(self) -> MultiMapView[Guid, ProjectId]:
        return MultiMapView(self._duplicated_guids)

    def undeclared_projects(
            self
    ) -> Iterator[tuple[ProjectId, SetView[ProjectId]]]:
        for project, undeclared in self._project_undeclared.items():
            yield (project, SetView(undeclared))

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

    def incompatible_projects(self) -> SetView[ProjectId]:
        return self._registry.incompatible()

    def cyclic_projects(self) -> SetView[ProjectId]:
        return SetView(self._project_cyclic)

    def __str__(self):
        return f"Solution({self.path})"


__all__ = ["Solution"]
