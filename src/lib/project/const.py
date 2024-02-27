from enum import StrEnum

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
    def id(self) -> str:
        return "Configuration"

    @classmethod
    def members(self) -> "set[Configuration]":
        return set(self)

    @classmethod
    def values(self) -> list[str]:
        return list(map(str, self.members()))

    @classmethod
    def from_string(self, value: str) -> "Configuration":
        for item in self:
            if item.value == value:
                return item
        raise KeyError(value)


class Platform(StrEnum):

    ANY_CPU = "AnyCPU"
    X86 = "x86"

    @classmethod
    def id(self) -> str:
        return "Platform"

    @classmethod
    def members(self) -> "set[Platform]":
        return set(self)

    @classmethod
    def values(self) -> list[str]:
        return list(map(str, self.members()))

    @classmethod
    def from_string(self, value: str) -> "Platform":
        for item in self:
            if item.value == value:
                return item
        raise KeyError(value)


class OutputType(StrEnum):

    EXE = "Exe"
    LIB = "Library"

    def to_extension(self) -> str:
        match self:
            case self.EXE: return "exe"
            case self.LIB: return "dll"
            case _: assert False

    @classmethod
    def members(self) -> "set[OutputType]":
        return set(self)

    @classmethod
    def values(self) -> list[str]:
        return list(map(str, self.members()))

    @classmethod
    def from_string(self, value: str) -> "OutputType":
        match value.upper():
            case "EXE" | "WINEXE": return self.EXE
            case "LIBRARY": return self.LIB
            case _: raise KeyError(value)
