import enum
import string

from dataclasses import dataclass

from enum import Enum
from collections.abc import Callable, Hashable, Iterable, Iterator
from typing import Generic, Optional, TypeVar, Union


_PO_A = TypeVar("_PO_A")


@dataclass
class Ok(Generic[_PO_A]):
    ok: _PO_A


_PE_A = TypeVar("_PE_A")


@dataclass
class Err(Generic[_PE_A]):
    err: _PE_A


_PR_A = TypeVar("_PR_A")
_PR_E = TypeVar("_PR_E")


Result = Union[Ok[_PR_A], Err[_PR_E]]


_LA_T = TypeVar("_LA_T")


class Lookahead(Generic[_LA_T]):

    _it: Iterator[_LA_T]
    _done: bool
    _next: _LA_T

    def __init__(self, source: Iterable[_LA_T]):
        self._it = iter(source)
        self._done = False
        self.step()

    @property
    def done(self) -> bool:
        return self._done

    def peek(self) -> _LA_T:
        if self._done:
            raise StopIteration("end of input")
        return self._value

    def step(self) -> bool:
        try:
            self._value = next(self._it)
        except StopIteration:
            self._done = True
        return not self._done


def takewhile(pred: Callable[[str], bool], source: Lookahead[str]) -> str:
    accum = []
    while not source.done:
        ch = source.peek()
        if not pred(ch):
            break
        accum.append(ch)
        source.step()
    return "".join(accum)

def dropwhile(pred: Callable[[str], bool], source: Lookahead[str]):
    while not source.done:
        ch = source.peek()
        if not pred(ch):
            break
        source.step()

def drop_whitespace(source: Lookahead[str]):
    dropwhile(lambda ch: ch in string.whitespace, source)


class ParseErr:
    END_OF_INPUT = 0


@dataclass
class Identifier:
    name: str


@dataclass
class StringLiteral:
    value: str


@dataclass
class EndOfInput:
    pass


Token = Union[EndOfInput, Identifier, StringLiteral]
