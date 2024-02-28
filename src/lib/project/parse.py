import enum
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generic, Literal, Self, TypeVar, Union, assert_never
import string

_S = TypeVar("_S")
_A = TypeVar("_A")
_B = TypeVar("_B")
_C = TypeVar("_C")


class ResultABC(ABC, Generic[_A, _B]):

    @abstractmethod
    def is_ok(self) -> bool:
        ...

    @abstractmethod
    def is_err(self) -> bool:
        ...

    @abstractmethod
    def inspect(self, fun: Callable[[_B], None]) -> Self:
        ...

    @abstractmethod
    def map(self, fun: Callable[[_B], _C]) -> "Result[_A, _C]":
        ...

    @abstractmethod
    def map_or(self, _: Callable[[_B], _C], value: _C) -> _C:
        ...

    @abstractmethod
    def and_then(self, fun: "Callable[[_B], Result[_A, _C]]") -> "Result[_A, _C]":
        ...

    @abstractmethod
    def or_else(self, fun: "Callable[[_A], Result[_C, _B]]") -> "Result[_C, _B]":
        ...

    @abstractmethod
    def unwrap_or(self, value: _B) -> _B:
        ...

@dataclass
class Err(ResultABC[_A, _B]):
    error: _A

    def is_err(self) -> Literal[True]:
        return True

    def is_ok(self) -> Literal[False]:
        return False

    def inspect(self, fun: Callable[[_B], None]) -> Self:
        return self

    def map(self, _: Callable[[_B], _C]) -> "Err[_A, _C]":
        return Err(self.error)

    def map_or(self, _: Callable[[_B], _C], value: _C) -> _C:
        return value

    def and_then(self, _: "Callable[[_B], Result[_A, _C]]") -> "Result[_A, _C]":
        return Err(self.error)

    def or_else(self, fun: "Callable[[_A], Result[_C, _B]]") -> "Result[_C, _B]":
        return fun(self.error)

    def unwrap_or(self, value: _B) -> _B:
        return value

@dataclass
class Ok(ResultABC[_A, _B]):
    value: _B

    def is_err(self) -> Literal[False]:
        return False

    def is_ok(self) -> Literal[True]:
        return True

    def inspect(self, fun: Callable[[_B], None]) -> Self:
        fun(self.value)
        return self

    def map(self, fun: Callable[[_B], _C]) -> "Ok[_A, _C]":
        return Ok(fun(self.value))

    def map_or(self, fun: Callable[[_B], _C], value: _C) -> _C:
        return fun(self.value)

    def and_then(self, fun: "Callable[[_B], Result[_A, _C]]") -> "Result[_A, _C]":
        return fun(self.value)

    def or_else(self, _: "Callable[[_A], Result[_C, _B]]") -> "Result[_C, _B]":
        return Ok(self.value)

    def unwrap_or(self, _: _B) -> _B:
        return self.value


Result = Union[Err[_A, _B], Ok[_A, _B]]


class Source(Generic[_S]):

    def __init__(self, data: Sequence[_S], index: int = 0):
        self._data = data
        self._index = 0

    def clone(self) -> "Source[_S]":
        return Source(self._data, self._index)

    @property
    def index(self) -> int:
        return self._index

    @property
    def done(self) -> bool:
        return self._index >= len(self._data)

    @property
    def item(self) -> _S:
        if self.done:
            raise StopIteration()
        return self._data[self._index]

    def step(self) -> bool:
        if self.done:
            return False
        self._index += 1
        return not self.done

    def backtrack(
            self,
            fun: "Callable[[Source[_S]], Result[_A, _B]]"
    ) -> Result[_A, _B]:

        other = self.clone()

        def commit(_: Any):
            self._index = other._index

        return fun(other).inspect(commit)


ParseFun = Callable[[Source[_S]], Result[_A, _B]]


class ParseErrorKind(Enum):
    END_OF_INPUT = 0,
    NO_MATCH = enum.auto()


@dataclass
class ParseError:
    kind: ParseErrorKind
    where: int


def takewhile(fun: Callable[[_S], bool]) -> ParseFun[_S, _A, list[_S]]:
    def go(source: Source[_S]) -> Result[_A, list[_S]]:
        items = []
        while not source.done:
            item = source.item
            if not fun(item):
                break
            items.append(item)
            source.step()
        return Ok(items)

    return go


def dropwhile(fun: Callable[[_S], bool]) -> ParseFun[_S, _A, None]:
    def go(source: Source[_S]) -> Result[_A, None]:
        while not source.done:
            item = source.item
            if not fun(item):
                break
            source.step()
        return Ok(None)

    return go


def literal(data: str) -> ParseFun[str, ParseError, str]:
    def go(source: Source[str]) -> Result[ParseError, str]:
        for index in range(0, len(data)):
            if source.done:
                return Err(
                    ParseError(ParseErrorKind.END_OF_INPUT, source.index)
                )
            item = source.item
            if data[index] != item:
                return Err(ParseError(ParseErrorKind.NO_MATCH, source.index))
            index += 1
            source.step()
        return Ok(data)
    return go


def sum(
        lhs: ParseFun[_S, ParseError, _B],
        rhs: ParseFun[_S, ParseError, _B],
        *rest: ParseFun[_S, ParseError, _B]
):
    def go(source: Source[_S]) -> Result[ParseError, _B]:
        result = source.backtrack(lhs)
        if result.is_ok():
            return result
        result = source.backtrack(rhs)
        if result.is_ok():
            return result
        for fun in rest:
            result = source.backtrack(fun)
            if result.is_ok():
                return result
        return Err(ParseError(ParseErrorKind.NO_MATCH, source.index))
    return go


def product(
        lhs: ParseFun[_S, ParseError, _B],
        rhs: ParseFun[_S, ParseError, _B],
        *rest: ParseFun[_S, ParseError, _B]
):
    def go(source: Source[_S]) -> Result[ParseError, list[_B]]:
        accum = []
        match lhs(source):
            case Ok(value):
                accum.append(value)
            case Err(err):
                return Err(err)
        match rhs(source):
            case Ok(value):
                accum.append(value)
            case Err(err):
                return Err(err)
        for fun in rest:
            match fun(source):
                case Ok(value):
                    accum.append(value)
                case Err(err):
                    return Err(err)
        return Ok(accum)
    return go
