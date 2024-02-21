from collections.abc import (
    Hashable, Iterable, Iterator,
    Mapping, Set,
    KeysView, ValuesView, ItemsView
)
from typing import Generic, Optional, TypeVar, overload

from .data_view import SetView


_MMVV_V = TypeVar("_MMVV_V", bound=Hashable)


class MultiMapValuesView(ValuesView[SetView[_MMVV_V]]):

    def __init__(self, view: ValuesView[set[_MMVV_V]]):
        self._view = view

    def __len__(self) -> int:
        return len(self._view)

    def __iter__(self) -> Iterator[SetView[_MMVV_V]]:
        for item in iter(self._view):
            yield SetView(item)

    def __contains__(self, value: object) -> bool:
        return value in self._view


_MMIV_K = TypeVar("_MMIV_K", bound=Hashable)
_MMIV_V = TypeVar("_MMIV_V", bound=Hashable)


class MultiMapItemsView(ItemsView[_MMIV_K, SetView[_MMIV_V]]):

    def __init__(self, view: ItemsView[_MMIV_K, set[_MMIV_V]]):
        self._view = view

    def __len__(self) -> int:
        return len(self._view)

    def __iter__(self) -> Iterator[tuple[_MMIV_K, SetView[_MMIV_V]]]:
        for key, value in iter(self._view):
            yield (key, SetView(value))

    def __contains__(self, value: object) -> bool:
        return value in self._view


_MM_K = TypeVar("_MM_K", bound=Hashable)
_MM_V = TypeVar("_MM_V", bound=Hashable)


class MultiMap(Generic[_MM_K, _MM_V]):

    _data: dict[_MM_K, set[_MM_V]]

    def __init__(self, items: Optional[Iterable[tuple[_MM_K, _MM_V]]] = None):
        self._data = dict()
        if items is not None:
            for (key, value) in items:
                self.add(key, value)

    def key_count(self) -> int:
        return len(self._data)

    def value_count(self) -> int:
        count = 0
        for value_set in self._data.values():
            count += len(value_set)
        return count

    def __len__(self) -> int:
        return self.key_count()

    def has_key(self, key: _MM_K) -> bool:
        return key in self._data;

    def has_item(self, key: _MM_K, value: _MM_V) -> bool:
        return key in self._data and value in self._data[key]

    @overload
    def __contains__(self, key: _MM_K) -> bool:
        ...

    @overload
    def __contains__(self, item: tuple[_MM_K, _MM_V]) -> bool:
        ...

    def __contains__(self, item):
        if isinstance(item, tuple):
            (k, v) = item
            return self.has_item(k, v)
        return self.has_key(item)

    def __getitem__(self, key: _MM_K) -> SetView[_MM_V]:
        return SetView(self._data[key])

    def __delitem__(self, key: _MM_K):
        del self._data[key]

    def add(self, key: _MM_K, value: _MM_V):
        if key in self._data:
            value_set = self._data[key]
        else:
            value_set = set()
            self._data[key] = value_set
        value_set.add(value)

    def remove(self, key: _MM_K, value: _MM_V):
        value_set = self._data[key]
        value_set.remove(value)
        if len(value_set) <= 0:
            del self._data[key]

    def __iter__(self) -> Iterator[_MM_K]:
        return iter(self._data)

    def keys(self) -> KeysView[_MM_K]:
        return self._data.keys()

    def values(self) -> MultiMapValuesView[_MM_V]:
        return MultiMapValuesView(self._data.values())

    def items(self) -> MultiMapItemsView[_MM_K, _MM_V]:
        return MultiMapItemsView(self._data.items())


_MMV_K = TypeVar("_MMV_K", bound=Hashable)
_MMV_V = TypeVar("_MMV_V", bound=Hashable)


class MultiMapView(Mapping[_MMV_K, SetView[_MMV_V]]):

    def __init__(self, data: MultiMap[_MMV_K, _MMV_V]):
        self._data = data

    def __len__(self) -> int:
        return len(self._data)

    def __getitem__(self, key: _MMV_K) -> SetView[_MMV_V]:
        return self._data[key]

    def __iter__(self) -> Iterator[_MMV_K]:
        return iter(self._data)


__all__ = [
    "MultiMap", "MultiMapView",
    "MultiMapValuesView", "MultiMapItemsView"
]
