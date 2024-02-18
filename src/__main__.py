import os
import re
import subprocess
import sys

import xml.dom.minidom as xml

from collections.abc import Iterable
from argparse import ArgumentParser
from pathlib import Path, PureWindowsPath
from typing import NewType


parser = ArgumentParser(
  prog="repo-dependency-analyzer",
  description="Multi-project dependency analysis."
)
parser.add_argument(
  "-r", "--root",
  dest="root",
  default=".",
  help="subtree of the repository in which to search"
)
parser.add_argument(
  "repo",
  metavar="REPOSITORY",
  help="repository in which to search"
)


def _normalize_windows_path(path: str | Path) -> Path:
    return Path(os.path.normpath(Path(*PureWindowsPath(path).parts)))


def _normalize_windows_relpath(context: Path, path: str | Path) -> Path:
    rel_path = PureWindowsPath(path)
    denorm_path = context.joinpath(rel_path)
    return Path(os.path.normpath(denorm_path))


_path_has_leading_subst_regexp = re.compile(r"\$\([^\)]*\).*")


def _path_has_leading_subst(path: str | Path) -> bool:
    return _path_has_leading_subst_regexp.match(str(path)) is not None


def run_find(*args, **kwargs):
    if "capture_output" not in kwargs:
        kwargs["capture_output"] = True
    if "check" not in kwargs:
        kwargs["check"] = True
    if "text" not in kwargs:
        kwargs["text"] = True
    return subprocess.run(["fd", *args], **kwargs)


def find_solutions(repo):
    return run_find(".sln$", repo)


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


def _build_parse_project_regexp():
    prefix = r'.*Project[^=]*=\s*'
    name = r'"(?P<name>[^"]*)"\s*'
    path = r'"(?P<path>[^"]*\.csproj)"\s*'
    guid = r'"\{(?P<guid>[^\}]*)\}"\s*'
    sep = r',\s*'
    return re.compile(''.join([prefix, name, sep, path, sep, guid]))


def _build_parse_assembly_name_regexp():
    return re.compile(r'\s*(?P<name>[^\s,]*)\s*,?')


Guid = NewType("Guid", str)


class AssemblyId:

    def __init__(
            self,
            name: str, path: None | Path,
            is_nuget_assembly: bool = False
    ):
        self._name = name
        self._path = path
        self._is_nuget_assembly = bool(is_nuget_assembly)

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> None | Path:
        return self._path

    @property
    def is_nuget_assembly(self) -> bool:
        return self._is_nuget_assembly

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, AssemblyId) and
            self._name == other._name and
            self._path == other._path and
            self._is_nuget_assembly == other._is_nuget_assembly
        )

    def __hash__(self) -> int:
        return hash((self._name, self._path))

    def __str__(self):
        return "".join([
            f"AssemblyId({self.name}, {self.path}, ",
            f"is_nuget_assembly={self.is_nuget_assembly})"
        ])



class ProjectId:

    def __init__(self, name: str, path: str | Path, guid: Guid):
        self._name = name
        self._path = Path(path)
        self._guid = guid

    @property
    def name(self):
        return self._name

    @property
    def path(self):
        return self._path

    @property
    def guid(self):
        return self._guid

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, ProjectId) and
            self._guid == other._guid and
            self._name == other._name and
            self._path == other._path
        )

    def __hash__(self) -> int:
        return hash((self._name, self._path, self._guid))

    def __str__(self):
        return f"ProjectId({self.name}, {self.path}, {self.guid})"


class SourceId:

    def __init__(self, name: str, path: Path):
        self._name = name
        self._path = path

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self._path

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, SourceId) and
            self._name == other._name and
            self._path == other._path
        )

    def __hash__(self) -> int:
        return hash((self._name, self._path))

    def __str__(self):
        return f"SourceId({self.name}, {self.path})"


class Project:

    _project_ref_ids: dict[Guid, ProjectId]
    # note: we are not using is_nuget_assembly as a distinguishing factor
    _assembly_ref_ids: dict[str, dict[None | Path, AssemblyId]]
    _source_ref_ids: dict[Path, SourceId]

    _PARSE_ASSEMBLY_NAME_REGEXP = _build_parse_assembly_name_regexp()

    def __init__(self, project_id: ProjectId):
        self._project_id = project_id
        self._assembly_ref_ids = dict()
        self._project_ref_ids = dict()
        self._source_ref_ids = dict()
        self._load()

    @classmethod
    def load(cls, project_id: ProjectId) -> "None | Project":
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
        return _normalize_windows_relpath(context, path)

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

    def _load_assembly_ref(self, assembly_ref: xml.Element):
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
                    name = _normalize_windows_path(name).stem

        # Now we're free to normalize our path (if we have one).
        if path is not None:
            if _path_has_leading_subst(path):
                path = _normalize_windows_path(path)
            else:
                path = self._normalize_relpath(path)

        return AssemblyId(name, path, is_nuget_assembly)

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

    def _load_project_ref(self, project_ref: xml.Element):
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

    def _load_source_ref(self, root: xml.Element):
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


class Solution:

    _path: Path
    _project_roots: dict[Guid, ProjectId]
    _project_registry: dict[Guid, Project]
    _project_dangling: dict[Guid, ProjectId]
    _assembly_dangling: set[AssemblyId]
    _source_dangling: set[SourceId]

    _PARSE_PROJECT_REGEXP = _build_parse_project_regexp()

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._project_roots = dict()
        self._project_registry = dict()
        self._project_dangling = dict()
        self._assembly_dangling = set()
        self._source_dangling = set()
        self._load()

    def _parse_project(self, line):

        match = self._PARSE_PROJECT_REGEXP.match(line)
        if match is None:
            return None
        name = match.group("name")
        path = match.group("path")
        guid = match.group("guid")

        repo_path = _normalize_windows_relpath(self.path.parent, path)

        return ProjectId(name, repo_path, Guid(guid))

    def _load_projects(self):
        stack = []
        for guid in self._project_roots:
            stack.append(self._project_roots[guid])
        while len(stack) > 0:
            project_id = stack.pop()
            guid = project_id.guid
            assert guid not in self._project_registry
            assert guid not in self._project_dangling
            project = Project.load(project_id)
            if project is None:
                self._project_dangling[guid] = project_id
            else:
                self._project_registry[guid] = Project(project_id)
                for project_id in project.project_refs():
                    if not (guid in self._project_registry or
                            guid in self._project_dangling):
                        stack.append(project_id)

    def _load_roots(self):
        with open(self._path, "r") as file:
            for line in file.readlines():
                project = self._parse_project(line)
                if project:
                    self._project_roots[project.guid] = project

    def _scan_projects(self):
        for project in self._project_registry.values():
            for assembly in project.assembly_refs():
                path = assembly.path
                if path is not None and not path.exists():
                    self._assembly_dangling.add(assembly)
            for source in project.source_refs():
                if not source.path.exists():
                    self._source_dangling.add(source)

    def _load(self):
        self._load_roots()
        self._load_projects()
        self._scan_projects()

    @property
    def path(self):
        return self._path

    def project_roots(self) -> Iterable[ProjectId]:
        return self._project_roots.values()

    def projects(self) -> Iterable[ProjectId]:
        return self._project_registry.values()

    def dangling_projects(self) -> Iterable[ProjectId]:
        return self._project_dangling.values()

    def dangling_assemblies(self) -> Iterable[AssemblyId]:
        return iter(self._assembly_dangling)

    def dangling_sources(self) -> Iterable[SourceId]:
        return iter(self._source_dangling)

    # def __contains__(self, item: Guid | ProjectId) -> bool:
    #     guid = item.guid if isinstance(item, ProjectId) else item
    #     return guid in self._project_roots

    # def __getitem__(self, key: Guid) -> ProjectId:
    #     return self._project_roots[key]

    def __str__(self):
        return f"Solution({self.path})"


args = parser.parse_args()
repo = Path(args.repo)

for line in find_solutions(repo).stdout.splitlines():
    solution = Solution(line)
    for project_id in solution.dangling_projects():
        print(project_id)
    for assembly_id in solution.dangling_assemblies():
        print(assembly_id)
    for source_id in solution.dangling_sources():
        print(source_id)
    break