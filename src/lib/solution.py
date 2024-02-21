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
from .id import AssemblyId, Guid, ProjectId, SourceId
from .data_view import SetView
from .multimap import (
    MultiMap, MultiMapView, MultiMapItemsView, MultiMapValuesView
)
from .project import (
    Project,
    ProjectLoadOk, ProjectLoadDangling, ProjectLoadCycle,
    ProjectLoadResult
)
from .project_registry import ProjectRegistry


def _build_parse_project_regexp():
    prefix = r'.*Project[^=]*=\s*'
    name = r'"(?P<name>[^"]*)"\s*'
    path = r'"(?P<path>[^"]*\.csproj)"\s*'
    guid = r'"\{(?P<guid>[^\}]*)\}"\s*'
    sep = r',\s*'
    return re.compile(''.join([prefix, name, sep, path, sep, guid]))


class Solution:

    # TODO: track the source of the broken stuff

    _path: Path
    _registry: ProjectRegistry
    _project_guids: dict[Guid, ProjectId]
    _project_roots: dict[Guid, ProjectId]
    _project_registry: dict[Guid, Project]
    _project_parents: MultiMap[ProjectId, ProjectId]
    _project_guid_duplicates: MultiMap[Guid, ProjectId]
    _project_undeclared: MultiMap[ProjectId, ProjectId]
    _project_dangling: dict[Guid, ProjectId]
    _assembly_dangling: MultiMap[ProjectId, AssemblyId]
    _source_dangling: MultiMap[ProjectId, SourceId]

    _PARSE_PROJECT_REGEXP = _build_parse_project_regexp()

    def __init__(self, path: str | Path):
        self._path = util.normalize_windows_path(path)
        self._registry = ProjectRegistry()
        self._project_guids = dict()
        self._project_roots = dict()
        self._project_registry = dict()
        self._project_parents = MultiMap()
        self._project_guid_duplicates = MultiMap()
        self._project_undeclared = MultiMap()
        self._project_dangling = dict()
        self._assembly_dangling = MultiMap()
        self._source_dangling = MultiMap()
        self._load()

    def _parse_project(self, line):

        match = self._PARSE_PROJECT_REGEXP.match(line)
        if match is None:
            return None
        name = match.group("name")
        path = match.group("path")
        guid = match.group("guid")

        repo_path = util.normalize_windows_relpath(self.path.parent, path)

        return ProjectId(name, repo_path, Guid(guid))

    def _load_projects(self):
        # this is insufficient for when projects may import one another ..
        stack = []
        for guid in self._project_roots:
            stack.append(self._project_roots[guid])
        while len(stack) > 0:
            project_id = stack.pop()
            guid = project_id.guid
            if guid in self._project_registry:
                other = self._project_registry[guid].project_id
                if other != project_id:
                    self._project_guid_duplicates.add(guid, other)
                    self._project_guid_duplicates.add(guid, project_id)
            elif guid not in self._project_dangling:
                project = Project.load(self._registry, project_id)
                match project:
                    case ProjectLoadDangling(_):
                        self._project_dangling[guid] = project_id
                    case ProjectLoadOk(project):
                        self._project_registry[guid] = project
                        for project_id in project.project_refs():
                            self._project_parents.add(project_id, project.project_id)
                            stack.append(project_id)
                    case _:
                        raise NotImplementedError()

    def _load_roots(self):
        with open(self._path, "r") as file:
            for line in file.readlines():
                project = self._parse_project(line)
                if project:
                    self._project_roots[project.guid] = project

    def topsort(self) -> tuple[bool, list[ProjectId]]:

        class Mark(Enum):
            WHITE = 0
            GREY = enum.auto()
            BLACK = enum.auto()

        marks: dict[ProjectId, Mark] = dict()
        output = []

        def visit(project_id: ProjectId) -> Optional[list[ProjectId]]:
            assert isinstance(project_id, ProjectId)
            match marks.get(project_id, Mark.WHITE):
                case Mark.GREY:
                    return [project_id]
                case Mark.BLACK:
                    return None
            if project_id.guid in self._project_dangling:
                marks[project_id] = Mark.BLACK
                output.append(project_id)
                return None
            marks[project_id] = Mark.GREY
            project = self._project_registry[project_id.guid]
            for subproject_id in project.project_refs():
                result = visit(subproject_id)
                if result is not None:
                    result.append(project_id)
                    return result
            marks[project_id] = Mark.BLACK
            output.append(project_id)
            return None

        for guid in self._project_roots:
            root_id = self._project_roots[guid]
            result = visit(root_id)
            if result is not None:
                result.append(root_id)
                result.reverse()
                return (False, result)

        output.reverse()
        return (True, output)

    def _scan_projects(self):

        for project in self._project_registry.values():
            project_id = project.project_id
            for subproject_id in project.project_refs():
                if subproject_id.guid not in self._project_roots:
                    self._project_undeclared.add(project_id, subproject_id)
            for assembly in project.assembly_refs():
                path = assembly.path
                if path is not None and not path.exists():
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

    def project_roots(self) -> ValuesView[ProjectId]:
        return self._project_roots.values()

    def project_parents(self) -> MultiMapView[ProjectId, ProjectId]:
        return MultiMapView(self._project_parents)

    def projects(self) -> ValuesView[Project]:
        return self._project_registry.values()

    @property
    def is_broken(self) -> bool:
        return (
            self.has_duplicated_guids or
            self.has_undeclared_projects or
            self.has_dangling_projects or
            self.has_dangling_assemblies or
            self.has_dangling_sources
        )

    @property
    def has_duplicated_guids(self) -> bool:
        return len(self._project_guid_duplicates) > 0

    @property
    def has_undeclared_projects(self) -> bool:
        return len(self._project_undeclared) > 0

    @property
    def has_dangling_projects(self) -> bool:
        return len(self._project_dangling) > 0

    @property
    def has_dangling_assemblies(self) -> bool:
        return len(self._assembly_dangling) > 0

    @property
    def has_dangling_sources(self) -> bool:
        return len(self._source_dangling) > 0

    def duplicated_guids(self) -> MultiMapView[Guid, ProjectId]:
        return MultiMapView(self._project_guid_duplicates)

    def undeclared_projects(
            self
    ) -> Iterator[tuple[ProjectId, SetView[ProjectId]]]:
        for project, undeclared in self._project_undeclared.items():
            yield (project, SetView(undeclared))

    # _project_roots: dict[Guid, ProjectId]
    # _project_registry: dict[Guid, Project]
    # _project_undeclared: dict[ProjectId, set[ProjectId]]
    # _project_dangling: dict[Guid, ProjectId]
    # _assembly_dangling: dict[ProjectId, set[AssemblyId]]
    # _source_dangling: dict[ProjectId, set[SourceId]]

    def dangling_projects(self) -> ValuesView[ProjectId]:
        return self._project_dangling.values()

    def dangling_assemblies(
            self
    ) -> MultiMapView[ProjectId, AssemblyId]:
        return MultiMapView(self._assembly_dangling)

    def dangling_sources(
            self
    ) -> MultiMapView[ProjectId, SourceId]:
        return MultiMapView(self._source_dangling)

    # def __contains__(self, item: Guid | ProjectId) -> bool:
    #     guid = item.guid if isinstance(item, ProjectId) else item
    #     return guid in self._project_roots

    # def __getitem__(self, key: Guid) -> ProjectId:
    #     return self._project_roots[key]

    def __str__(self):
        return f"Solution({self.path})"


__all__ = ["Solution"]