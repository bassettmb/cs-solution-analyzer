from collections.abc import Iterator, Mapping, Sequence, Set
from typing import TypeVar, overload


_K1 = TypeVar("_K1")
_V1 = TypeVar("_V1")


class MapView(Mapping[_K1, _V1]):

    def __init__(self, data: Mapping[_K1, _V1]):
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key: _K1) -> _V1:
        return self._data[key]

    def __iter__(self) -> Iterator[_K1]:
        return iter(self._data)


_V3 = TypeVar("_V3")


class SequenceView(Sequence[_V3]):

    def __init__(self, data: Sequence[_V3]):
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    @overload
    def __getitem__(self, index: int) -> _V3:
        ...

    @overload
    def __getitem__(self, slice: slice) -> list[_V3]:
        ...

    def __getitem__(self, selector):
        return self._data[selector]

    def __iter__(self) -> Iterator[_V3]:
        return iter(self._data)


_V4 = TypeVar("_V4")


class SetView(Set[_V4]):

    def __init__(self, data: Set[_V4]):
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    @overload
    def __contains__(self, value: _V4) -> bool:
        ...

    # Sigh. Set inherits from Container instead of Container[_V4].
    # So. We have to provide a type-erased overload.
    @overload
    def __contains__(self, value: object) -> bool:
        ...

    def __contains__(self, value):
        return value in self._data

    def __iter__(self) -> Iterator[_V4]:
        return iter(self._data)


__all__ = ["MapView", "SequenceView", "SetView"]
