import re

import xml.dom.minidom as xml

from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from . import util

from .id import AssemblyId, Guid, Name, ProjectId, SourceId


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


class Project:

    _project_ref_ids: dict[Guid, ProjectId]
    # note: we are not using is_nuget_assembly as a distinguishing factor
    _assembly_ref_ids: dict[Name, dict[Optional[Path], AssemblyId]]
    _source_ref_ids: dict[Path, SourceId]
    _import_ids = dict[Guid, ProjectId]

    _PARSE_ASSEMBLY_NAME_REGEXP = _build_parse_assembly_name_regexp()

    def __init__(self, project_id: ProjectId):
        self._project_id = project_id
        self._assembly_ref_ids = dict()
        self._project_ref_ids = dict()
        self._source_ref_ids = dict()
        self._imports = dict()
        self._load()

    @classmethod
    def load(cls, project_id: ProjectId) -> "Optional[Project]":
        if not project_id.path.exists():
            return None
        return cls(project_id)

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    def assembly_refs(self) -> Iterable[AssemblyId]:
        for path_map in self._assembly_ref_ids.values():
            for assembly_id in path_map.values():
                yield assembly_id

    def project_refs(self) -> Iterable[ProjectId]:
        return self._project_ref_ids.values()

    def source_refs(self) -> Iterable[SourceId]:
        return self._source_ref_ids.values()

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

    def _add_project_id(self, project_id: ProjectId):
        guid = project_id.guid
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
    ) -> Optional[ProjectId]:
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

        return ProjectId(name, path, Guid(guid))

    def _load_project_refs(self, root: xml.Element):
        for project_ref in root.getElementsByTagName("ProjectReference"):
            project_id = self._load_project_ref(project_ref)
            if project_id is not None:
                self._add_project_id(project_id)

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

    def _load(self):
        with xml.parse(str(self._project_id.path)) as root:
            self._load_assembly_refs(root)
            self._load_project_refs(root)
            self._load_source_refs(root)


__all__ = ["Project"]
