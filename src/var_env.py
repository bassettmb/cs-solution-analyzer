from collections.abc import Hashable, Iterable
from typing import Generic, Optional, TypeVar


VarEnvName = TypeVar("VarEnvName", bound=Hashable)
VarEnvValue = TypeVar("VarEnvValue")


class VarEnv(Generic[VarEnvName, VarEnvValue]):

    _bindings: dict[VarEnvName, list[VarEnvValue]]
    _names: list[VarEnvName]
    _scopes: list[int]

    def __init__(
            self,
            bindings: Optional[Iterable[tuple[VarEnvName, VarEnvValue]]] = None
    ):
        self._bindings = dict()
        self._names = []
        self._scopes = []
        if bindings is not None:
            for name, value in bindings:
                self[name] = value

    def __len__(self) -> int:
        return len(self._bindings)

    def __contains__(self, name: VarEnvName) -> bool:
        return name in self._bindings

    def __getitem__(self, name: VarEnvName) -> VarEnvValue:
        values = self._bindings[name]
        return values[-1]

    def __setitem__(self, name: VarEnvName, value: VarEnvValue):
        self._names.append(name)
        if name in self._bindings:
            values = self._bindings[name]
        else:
            values = []
            self._bindings[name] = values
        values.append(value)

    def names(self) -> Iterable[VarEnvName]:
        for name in self._bindings:
            yield name

    def bindings(self) -> Iterable[tuple[VarEnvName, VarEnvValue]]:
        for name in self._bindings:
            yield (name, self[name])

    def __enter__(self) -> "VarEnv":
        self._scopes.append(len(self._names))
        return self

    def __exit__(self, *_exc):
        name_count = self._scopes.pop()
        while len(self._names) > name_count:
            name = self._names.pop()
            values = self._bindings[name]
            values.pop()
            if len(values) <= 0:
                del self._bindings[name]
