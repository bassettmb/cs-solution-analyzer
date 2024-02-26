from enum import StrEnum
from typing import Self

CONDITION: str = "Condition"
CONFIGURATION: str = "Configuration"
PLATFORM: str = "Platform"


class Configuration(StrEnum):

    DEBUG = "Debug"
    RELEASE = "Release"
    SETUP = "Setup"
    RETAIL = "Retail"
    NET20_DEBUG = "NET20-Debug"
    NET20_RELEASE = "NET20-Release"
    NET35_DEBUG = "NET35-Debug"
    NET35_RELEASE = "NET35-Release"
    NET40_DEBUG = "NET40-Debug"
    NET40_RELEASE = "NET40-Release"

    @classmethod
    def members(self) -> set[Self]:
        return set(self)

    @classmethod
    def values(self) -> list[str]:
        return list(map(str, self.members()))

    @classmethod
    def from_string(self, value: str) -> Self:
        for item in self:
            if item.value == value:
                return item
        raise KeyError(value)


class Platform(StrEnum):

    ANY_CPU = "AnyCPU"
    X86 = "x86"

    @classmethod
    def members(self) -> set[Self]:
        return set(self)

    @classmethod
    def values(self) -> list[str]:
        return list(map(str, self.members()))

    @classmethod
    def from_string(self, value: str) -> Self:
        for item in self:
            if item.value == value:
                return item
        raise KeyError(value)
