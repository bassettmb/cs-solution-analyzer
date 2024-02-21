from pathlib import Path
from typing import NewType, Optional


class Guid:

    def __init__(self, raw: str):
        self._raw = raw.upper()

    @property
    def raw(self) -> str:
        return self._raw

    def __hash__(self) -> int:
        return hash(self._raw)

    def __eq__(self, other) -> bool:
        return isinstance(other, Guid) and self._raw == other._raw

    def __str__(self) -> str:
        return self._raw


Name = NewType("Name", str)


class AssemblyId:

    def __init__(
            self,
            name: Name, path: Optional[Path],
            is_nuget_assembly: bool = False
    ):
        self._name = name
        self._path = path
        self._is_nuget_assembly = bool(is_nuget_assembly)

    @property
    def name(self) -> Name:
        return self._name

    @property
    def path(self) -> Optional[Path]:
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
