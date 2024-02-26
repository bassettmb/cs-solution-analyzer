import enum
import re

import xml.dom.minidom as xml

from collections.abc import Iterator, KeysView, ValuesView
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generic, NewType, Optional, Union, TypeVar, TYPE_CHECKING

from .. import util
from ..data_view import MapView
from ..id import AssemblyId, Guid, Name, ProjectId, SourceId
from ..multimap import MultiMap, MultiMapView
from ..var_env import VarEnv

from . import const
from .const import CONDITION, CONFIGURATION, PLATFORM
from .regexp import parse_condition


if TYPE_CHECKING:
    from .project_registry import ProjectRegistry

_path_has_leading_subst_regexp = re.compile(r"\$\([^\)]*\).*")


def _path_has_leading_subst(path: str | Path) -> bool:
    return _path_has_leading_subst_regexp.match(str(path)) is not None


def _get_xml_text(node: xml.Node) -> str:
    def go(node: xml.Node, accum: list[str]):
        for node in node.childNodes:
            if node.nodeType == xml.Node.TEXT_NODE:  # type: ignore
                accum.append(node.data)  # type: ignore
            elif node.nodeType == xml.Node.ELEMENT_NODE:  # type: ignore
                go(node, accum)
    accum: list[str] = []
    go(node, accum)
    return "".join(accum)


def _build_parse_assembly_name_regexp():
    return re.compile(r'\s*(?P<name>[^\s,]*)\s*,?')


PropertyName = NewType("PropertyName", str)
PropertyValue = NewType("PropertyValue", str)
ProjectEnv = NewType("ProjectEnv", VarEnv[PropertyName, PropertyValue])


_PLO_T = TypeVar("_PLO_T")


@dataclass
class ProjectLoadOk(Generic[_PLO_T]):
    project: _PLO_T


@dataclass
class ProjectLoadDangling:
    backtrace: list[ProjectId]


@dataclass
class ProjectLoadCycle:
    backtrace: list[ProjectId]


_PLR_T = TypeVar("_PLR_T")


ProjectLoadResult = Union[
    ProjectLoadOk[_PLR_T],
    ProjectLoadDangling,
    ProjectLoadCycle
]


class OutputType(Enum):
    EXE = 0
    LIB = enum.auto()

    @classmethod
    def from_string(self, string_repr: str) -> "Optional[OutputType]":
        match string_repr.upper():
            case "EXE" | "WINEXE": return self.EXE
            case "LIBRARY": return self.LIB
            case _: return None


class ProjectPropGroup:

    def __init__(
            self,
            output_type: OutputType,
            output_path: Path,
            assembly_name: str
    ):
        self._assembly_name = assembly_name
        self._output_path = output_path
        self._output_type = output_type

    @property
    def assembly_name(self) -> str:
        return self._assembly_name

    @property
    def output_path(self) -> Path:
        return self._output_path

    @property
    def output_type(self) -> OutputType:
        return self._output_type

    def __str__(self) -> str:
        return "".join([
            "SolutionPropGroup(",
            f"{self.output_type}, ",
            f"{self.output_path}, ",
            f"{self.assembly_name})"
        ])


class Project:

    _project_id: ProjectId
    _project_ref_ids: MultiMap[ProjectId, Guid]
    # note: we are not using is_nuget_assembly as a distinguishing factor
    _assembly_ref_ids: dict[Name, dict[Optional[Path], AssemblyId]]
    _source_ref_ids: dict[Path, SourceId]
    _props: dict[str, str]

    _PARSE_ASSEMBLY_NAME_REGEXP = _build_parse_assembly_name_regexp()

    def __init__(
            self,
            registry: "ProjectRegistry",
            project_id: ProjectId
    ):
        self._project_id = project_id
        self._assembly_ref_ids = dict()
        self._project_ref_ids = MultiMap()
        self._source_ref_ids = dict()
        self._props = dict()

    @classmethod
    def load(
            cls,
            registry: "ProjectRegistry",
            project_id: ProjectId
    ) -> "ProjectLoadResult[Project]":
        if not project_id.path.exists():
            return ProjectLoadDangling([project_id])
        project = cls(registry, project_id)
        return project._load(registry)

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    def assembly_refs(self) -> Iterator[AssemblyId]:
        for path_map in self._assembly_ref_ids.values():
            for assembly_id in path_map.values():
                yield assembly_id

    def project_refs(self) -> KeysView[ProjectId]:
        return self._project_ref_ids.keys()

    def project_ref_guids(self) -> MultiMapView[ProjectId, Guid]:
        return MultiMapView(self._project_ref_ids)

    def source_refs(self) -> ValuesView[SourceId]:
        return self._source_ref_ids.values()

    def properties(self) -> MapView[str, str]:
        return MapView(self._props)

    def _normalize_relpath(self, path: str | Path) -> Path:
        context = self.project_id.path.parent
        return util.normalize_windows_relpath(context, path)

    def _add_assembly_id(self, assembly_id: AssemblyId):
        name = assembly_id.name
        if name in self._assembly_ref_ids:
            path = assembly_id.path
            path_map = self._assembly_ref_ids[name]
            if path in path_map:
                present = path_map[path]
                if assembly_id != present:
                    raise RuntimeError(
                        "\n".join([
                            "distinct assemblies with the name and path???",
                            f"  old: {present}",
                            f"  new: {assembly_id}"
                        ])
                    )
            else:
                path_map[path] = assembly_id
        else:
            self._assembly_ref_ids[name] = {assembly_id.path: assembly_id}

    def _load_assembly_ref(
            self,
            assembly_ref: xml.Element
    ) -> Optional[AssemblyId]:
        # All references must(?) have an include attribute.
        if not assembly_ref.hasAttribute("Include"):
            return None

        # The include attribute will contain EITHER a name OR a path depending
        # on the structure of its subtree.

        # Plain assembly references are shaped like one of:
        #   <Reference Include="{name}[, ...]" HintPath={path}/>
        #   <Reference Include="{name}[, ...]">
        #     <HintPath>{path}</HintPath>
        #   </Reference>
        #  <Reference Include={path}/>
        # NuGet package references are shaped like:
        #   <Reference Include={path}>
        #     <NuGetPackageId>{name}</NuGetPackageId>
        #     ...
        #   </Reference>

        is_nuget_assembly = False
        name = assembly_ref.getAttribute("Include")
        path: str | Path | None = None

        for child in assembly_ref.childNodes:
            if child.nodeType == xml.Node.ELEMENT_NODE:
                if child.tagName == "NuGetPackageId":
                    # We have a NuGet package!
                    if path is None:
                        is_nuget_assembly = True
                        # As seen above, nuget package names for some reason
                        # live in the Include attribute of the Reference node.
                        path = name
                        name = _get_xml_text(child)
                elif child.tagName == "HintPath":
                    if path is None:
                        path = _get_xml_text(child)

        if not is_nuget_assembly:
            # With plain assembly references, the Include attribute is
            # permitted to be a comma-separated list of fields. We only care
            # about the leading element, however.
            match = self._PARSE_ASSEMBLY_NAME_REGEXP.match(name)
            if match is None:
                raise RuntimeError(f"strange assembly name: {name}")
            name = match.group("name")

            # If we don't have a nuget package and we didn't find a HintPath
            # element, then we check for existence of a HintPath attribute.
            if path is None:
                if assembly_ref.hasAttribute("HintPath"):
                    path = assembly_ref.getAttribute("HintPath")
                elif name.endswith(".dll"):
                    # Sometimes when we don't have a path, the Include
                    # attribute might have actually contained a path. I don't
                    # know if there's a good way to for sure when an assembly
                    # is held there, but we can check for a .dll extension.
                    path = name  # Just copy it, I guess?
                    name = util.normalize_windows_path(name).stem

        # Now we're free to normalize our path (if we have one).
        if path is not None:
            if _path_has_leading_subst(path):
                path = util.normalize_windows_path(path)
            else:
                path = self._normalize_relpath(path)

        return AssemblyId(Name(name), path, is_nuget_assembly)

    def _load_assembly_refs(self, root: xml.Document):
        for assembly_ref in root.getElementsByTagName("Reference"):
            assembly_id = self._load_assembly_ref(assembly_ref)
            if assembly_id is not None:
                self._add_assembly_id(assembly_id)

    def _add_project_id(self, guid: Guid, project_id: ProjectId):
        self._project_ref_ids.add(project_id, guid)

    def _load_project_ref(
            self,
            registry: "ProjectRegistry",
            project_ref: xml.Element
    ) -> Optional[ProjectLoadResult[tuple[Guid, ProjectId]]]:
        if not project_ref.hasAttribute("Include"):
            return None

        name = None
        guid = None

        for child in project_ref.childNodes:
            if child.nodeType == xml.Node.ELEMENT_NODE:
                if child.tagName == "Name":
                    if name is None:
                        name = _get_xml_text(child)
                elif child.tagName == "Project":
                    if guid is None:
                        guid = _get_xml_text(child)

        if name is None or guid is None:
            return None

        guid = guid.lstrip("{").rstrip("}")
        path = self._normalize_relpath(project_ref.getAttribute("Include"))

        return ProjectLoadOk((Guid(guid), ProjectId(name, path)))

    def _load_project_refs(
            self,
            registry: "ProjectRegistry",
            root: xml.Document
    ) -> ProjectLoadResult[None]:
        for project_ref in root.getElementsByTagName("ProjectReference"):
            result = self._load_project_ref(registry, project_ref)
            if result is not None:
                match result:
                    case ProjectLoadOk((guid, project_id)):
                        self._add_project_id(guid, project_id)
                    case ProjectLoadDangling(backtrace):
                        return ProjectLoadDangling(backtrace)
                    case ProjectLoadCycle(backtrace):
                        return ProjectLoadCycle(backtrace)
        return ProjectLoadOk(None)

    def _add_source_id(self, source_id: SourceId):
        path = source_id.path
        if path in self._source_ref_ids:
            present = self._source_ref_ids[path]
            if source_id != present:
                raise RuntimeError(
                    "\n".join([
                        "source files with identical paths but distinct names??",
                        f"  old: {present}",
                        f"  new: {source_id}"
                    ])
                )
        else:
            self._source_ref_ids[path] = source_id

    def _load_source_ref(self, root: xml.Element) -> Optional[list[SourceId]]:
        INCLUDE = "Include"
        if not root.hasAttribute(INCLUDE):
            return None
        # source Includes may contain more than one path, separated by semicolons
        sources = []
        for item in root.getAttribute(INCLUDE).split(";"):
            path_string = item.strip()
            if "" != path_string:
                path = self._normalize_relpath(path_string)
                name = path.name
                sources.append(SourceId(name, path))
        return None if len(sources) <= 0 else sources

    def _load_source_refs(self, root: xml.Document):
        for source_ref in root.getElementsByTagName("Compile"):
            sources = self._load_source_ref(source_ref)
            if sources is not None:
                for source_id in sources:
                    self._add_source_id(source_id)

    def _load_props(
            self,
            registry: "ProjectRegistry",
            root: xml.Element
    ):
        def match_condition(child, env):
            def match_env(key, value, env):
                return (
                    # always match if no value
                    value is None or
                    # otherwise, require match on env
                    (key in env and env[key] == value)
                )
            if not child.hasAttribute(CONDITION):
                return True  # no condition! always match
            configuration, platform = parse_condition(
                child.getAttribute(CONDITION)
            )
            return (
                match_env(CONFIGURATION, configuration, env) and
                match_env(PLATFORM, platform, env)
            )

        registry_config = registry.config()
        if CONFIGURATION in registry_config:
            self._props[CONFIGURATION] = registry_config[CONFIGURATION]
        if PLATFORM in registry_config:
            self._props[PLATFORM] = registry_config[PLATFORM]

        for prop_group in root.getElementsByTagName("PropertyGroup"):

            if not match_condition(prop_group, self._props):
                continue

            for child in prop_group.childNodes:
                if child.nodeType == xml.Node.ELEMENT_NODE:
                    match child.tagName:
                        case const.CONFIGURATION:
                            # pick up new configuration values
                            if match_condition(child, self._props):
                                self._props[CONFIGURATION] = _get_xml_text(
                                    child
                                )
                        case const.PLATFORM:
                            if match_condition(child, self._props):
                                self._props[PLATFORM] = _get_xml_text(child)
                        case None:
                            # hopefully this isn't reachable...
                            assert False
                        case tag_name:
                            self._props[tag_name] = _get_xml_text(child)




    # def _find_import(self, root: xml.Element) -> Option[ProjectId]:
    #     if not root.hasAttribute("Project"):
    #         return None
    #     path = self._normalize_relpath(root.getAttribute("Project"))
    #     name = path.name

    # def _find_imports(self, root: xml.Element): Iterable[ProjectId]
    #     for import_ref in root.getElementsByTagName("Import"):
    #         self._load_import_ref(import_ref)
    #         if project_id is not None:
    #             yield project_id

    def _load(self, registry: "ProjectRegistry") -> "ProjectLoadResult[Project]":
        with xml.parse(str(self._project_id.path)) as root:
            self._load_props(registry, root)
            self._load_assembly_refs(root)
            match self._load_project_refs(registry, root):
                case ProjectLoadDangling(backtrace):
                    return ProjectLoadDangling(backtrace)
                case ProjectLoadCycle(backtrace):
                    return ProjectLoadCycle(backtrace)
                case ProjectLoadOk(_):
                    pass
            self._load_source_refs(root)
        return ProjectLoadOk(self)


__all__ = [
    "Project", "PropertyName", "PropertyValue", "ProjectEnv",
    "ProjectLoadOk", "ProjectLoadDangling", "ProjectLoadCycle",
    "ProjectLoadResult", "ProjectPropGroup", "OutputType"
]
