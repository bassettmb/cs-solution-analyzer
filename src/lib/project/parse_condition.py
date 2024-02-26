import re

from typing import Optional

from .const import CONFIGURATION, PLATFORM

WHITESPACE = r"\s*"


def group(expr):
    return "(?:" + expr + ")"


def bracket(before, after, expr):
    return before + group(expr) + after


def quote(expr):
    return bracket("'", "'", expr)


def paren(expr):
    return bracket(r"\(", r"\)", expr)


def capture(name, expr):
    return "(?P<" + name + ">" + expr + ")"


def optional(expr):
    return group(expr) + "?"


def re_sum(fst, snd, *rest):
    return "|".join([fst, snd, *rest])


def re_product(fst, snd, *rest):
    return "".join([fst, snd, *rest])


def token(expr):
    return group(expr) + WHITESPACE


def build_var(expr):
    return r"\$" + paren(expr)


def build_eq_expr(lhs, rhs):
    return "".join([
        WHITESPACE,
        token(quote(lhs)),
        token("=="),
        token(quote(rhs))
    ])


_HAS_CONFIG = "has_config"
_HAS_PLATFORM = "has_platform"

has_config = build_var(CONFIGURATION)
has_platform = build_var(PLATFORM)
capturing_has_config = build_var(
    capture(_HAS_CONFIG, CONFIGURATION)
)
capturing_has_platform = build_var(
    capture(_HAS_PLATFORM, PLATFORM)
)

config_types = ["Debug", "Release", "Setup", "Retail"]
for dotnet_version in ["NET20", "NET35", "NET40"]:
    config_types.append(dotnet_version + "Debug")
    config_types.append(dotnet_version + "Release")

config = capture(CONFIGURATION, re_sum(*config_types))
platform = capture(PLATFORM, re_sum("AnyCPU", "x86"))

no_config_source = build_eq_expr(
    re_sum(
        re_product(has_config, r"\|", has_platform),
        has_config,
        has_platform
    ),
    ""
)
just_config_source = build_eq_expr(capturing_has_config, config)
just_platform_source = build_eq_expr(
    capturing_has_platform,
    platform
)
combined_source = build_eq_expr(
    re_product(
        capturing_has_config,
        r"\|",
        capturing_has_platform
    ),
    re_product(config, r"\|", platform)
)

no_config = re.compile(no_config_source)
just_config = re.compile(just_config_source)
just_platform = re.compile(just_platform_source)
combined = re.compile(combined_source)

def parse_condition(
        text: str,
        configuration: Optional[str] = None,
        platform: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    if match := just_config.match(text):
        configuration = match.group(CONFIGURATION)
    elif match := just_platform.match(text):
        platform = match.group(PLATFORM)
    elif match := combined.match(text):
        configuration = match.group(CONFIGURATION)
        platform = match.group(PLATFORM)
    return (configuration, platform)
