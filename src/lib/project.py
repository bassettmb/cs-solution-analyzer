import enum
import re

import xml.dom.minidom as xml

from collections.abc import Iterator, ValuesView
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NewType, Optional, Union, TYPE_CHECKING

from . import util
from .data_view import SequenceView
from .id import AssemblyId, Guid, Name, SimpleProjectId, ProjectId, SourceId
from .var_env import VarEnv

if TYPE_CHECKING:
    from .project_registry import ProjectRegistry

_path_has_leading_subst_regexp = re.compile(r"\$\([^\)]*\).*")


def _path_has_leading_subst(path: str | Path) -> bool:
    return _path_has_leading_subst_regexp.match(str(path)) is not None


def _get_xml_text(node: xml.Node) -> str:
    def go(node: xml.Node, accum: list[str]):
        for node in node.childNodes:
            if node.nodeType == xml.Node.TEXT_NODE:
                accum.append(node.data)
            elif node.nodeType == xml.Node.ELEMENT_NODE:
                go(node, accum)
    accum: list[str] = []
    go(node, accum)
    return "".join(accum)


def _build_parse_assembly_name_regexp():
    return re.compile(r'\s*(?P<name>[^\s,]*)\s*,?')


PropertyName = NewType("PropertyName", str)
PropertyValue = NewType("PropertyValue", str)
ProjectEnv = NewType("ProjectEnv", VarEnv[PropertyName, PropertyValue])


@dataclass
class ProjectLoadComplete:
    project: "Project"


@dataclass
class ProjectLoadDangling:
    backtrace: list[SimpleProjectId]


@dataclass
class ProjectLoadCycle:
    backtrace: list[SimpleProjectId]


ProjectLoadResult = Union[
    ProjectLoadComplete,
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

    _project_id: SimpleProjectId
    _project_ref_ids: dict[Guid, SimpleProjectId]
    # note: we are not using is_nuget_assembly as a distinguishing factor
    _assembly_ref_ids: dict[Name, dict[Optional[Path], AssemblyId]]
    _source_ref_ids: dict[Path, SourceId]
    _prop_groups: list[ProjectPropGroup]

    _PARSE_ASSEMBLY_NAME_REGEXP = _build_parse_assembly_name_regexp()

    def __init__(self, project_id: SimpleProjectId):
        self._project_id = project_id
        self._assembly_ref_ids = dict()
        self._project_ref_ids = dict()
        self._source_ref_ids = dict()
        self._prop_groups = list()
        self._load()

    @classmethod
    def load(
            cls,
            registry: "ProjectRegistry",
            project_id: SimpleProjectId
    ) -> ProjectLoadResult:
        if not project_id.path.exists():
            return ProjectLoadDangling([project_id])
        return ProjectLoadComplete(cls(project_id))

    @property
    def project_id(self) -> SimpleProjectId:
        return self._project_id

    def assembly_refs(self) -> Iterator[AssemblyId]:
        for path_map in self._assembly_ref_ids.values():
            for assembly_id in path_map.values():
                yield assembly_id

    def project_refs(self) -> set[ProjectId]:
        project_refs = set()
        for guid, simple_ref in self._project_ref_ids.items():
            project_refs.add(ProjectId(simple_ref.name, simple_ref.path, guid))
        return project_refs

    def source_refs(self) -> ValuesView[SourceId]:
        return self._source_ref_ids.values()

    def prop_groups(self) -> SequenceView[ProjectPropGroup]:
        return SequenceView(self._prop_groups)

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

    def _load_assembly_refs(self, root: xml.Element):
        for assembly_ref in root.getElementsByTagName("Reference"):
            assembly_id = self._load_assembly_ref(assembly_ref)
            if assembly_id is not None:
                self._add_assembly_id(assembly_id)

    def _add_project_id(self, guid: Guid, project_id: SimpleProjectId):
        if guid not in self._project_ref_ids:
            self._project_ref_ids[guid] = project_id
        else:
            present = self._project_ref_ids[guid]
            if project_id != present:
                raise RuntimeError(
                    "\n".join([
                        "distinct projects with the same guid???",
                        f"  old: {present}",
                        f"  new: {project_id}"
                    ])
                )

    def _load_project_ref(
            self,
            project_ref: xml.Element
    ) -> Optional[tuple[Guid, SimpleProjectId]]:
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

        return (Guid(guid), SimpleProjectId(name, path))

    def _load_project_refs(self, root: xml.Element):
        for project_ref in root.getElementsByTagName("ProjectReference"):
            result = self._load_project_ref(project_ref)
            if result is not None:
                guid, project_id = result
                self._add_project_id(guid, project_id)

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

    def _load_source_ref(self, root: xml.Element) -> Optional[SourceId]:
        if not root.hasAttribute("Include"):
            return None
        path = self._normalize_relpath(root.getAttribute("Include"))
        name = path.name
        return SourceId(name, path)

    def _load_source_refs(self, root: xml.Element):
        for source_ref in root.getElementsByTagName("Compile"):
            source_id = self._load_source_ref(source_ref)
            if source_id is not None:
                self._add_source_id(source_id)

    def _add_prop_group(self, prop_group: ProjectPropGroup):
        self._prop_groups.append(prop_group)

    def _load_prop_group(
            self,
            root: xml.Element
    ) -> Optional[ProjectPropGroup]:
        assembly_name = None
        output_path_string = None
        output_type_string = None
        for child in root.childNodes:
            if child.nodeType == xml.Node.ELEMENT_NODE:
                match child.tagName:
                    case "AssemblyName":
                        assembly_name = _get_xml_text(child)
                    case "OutputPath":
                        output_path_string = _get_xml_text(child)
                    case "OutputType":
                        output_type_string = _get_xml_text(child)
        if (
                assembly_name is None or
                output_path_string is None or
                output_type_string is None
        ):
            return None
        output_type = OutputType.from_string(output_type_string)
        if output_type is None:
            return None
        output_path = self._normalize_relpath(output_path_string)
        return ProjectPropGroup(output_type, output_path, assembly_name)

    def _load_prop_groups(self, root: xml.Element):
        for prop_node in root.getElementsByTagName("PropertyGroup"):
            prop_group = self._load_prop_group(prop_node)
            if prop_group is not None:
                self._add_prop_group(prop_group)

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

    def _load(self):
        with xml.parse(str(self._project_id.path)) as root:
            self._load_assembly_refs(root)
            self._load_project_refs(root)
            self._load_source_refs(root)
            self._load_prop_groups(root)


__all__ = [
    "Project", "PropertyName", "PropertyValue", "ProjectEnv",
    "ProjectLoadComplete", "ProjectLoadDangling", "ProjectLoadCycle",
    "ProjectLoadResult", "ProjectPropGroup", "OutputType"
]
