"""Tests for the 5 runtime pitfalls documented in
`@.claude/rules/library-and-stack.md` Partie B §7.

Each pitfall has a deterministic detector function in `sdd_lib` (or here
inline if very small). The tests assert that the detector matches a known
bad example and skips a known good example.

These tests are NOT a substitute for actual runtime testing of the 5
combos (C1-C5) — they guarantee that the documented anti-patterns can be
spotted statically by lint/audit, so a regression cannot silently sneak
back into a generated project.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# 7.1 CORS allowlist must contain BOTH localhost AND 127.0.0.1 for each port
# ---------------------------------------------------------------------------

def detect_cors_localhost_only(allowed_origins: list[str]) -> list[int]:
    """Return ports where only `localhost` is listed (missing 127.0.0.1)."""
    by_host = {"localhost": set(), "127.0.0.1": set()}
    for origin in allowed_origins:
        m = re.match(r"^https?://(localhost|127\.0\.0\.1):(\d+)$", origin)
        if m:
            by_host[m.group(1)].add(int(m.group(2)))
    only_localhost = by_host["localhost"] - by_host["127.0.0.1"]
    only_ip = by_host["127.0.0.1"] - by_host["localhost"]
    return sorted(only_localhost | only_ip)


def test_pitfall_71_cors_missing_ip_variant_detected():
    bad = ["http://localhost:5173", "http://localhost:4173"]
    assert detect_cors_localhost_only(bad) == [4173, 5173]


def test_pitfall_71_cors_full_allowlist_passes():
    good = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ]
    assert detect_cors_localhost_only(good) == []


# ---------------------------------------------------------------------------
# 7.2 <input type=number> coerces to number → state type mismatch (Vue/Angular)
# ---------------------------------------------------------------------------

def detect_input_number_string_state(source: str) -> list[str]:
    """Match `ref<string>(…)` or `signal<string>(…)` used alongside
    `<input type="number">` in the same component. Returns matched field names."""
    if 'type="number"' not in source and "type='number'" not in source:
        return []
    matches = []
    for m in re.finditer(r"(?:ref|signal)<string>\(\s*['\"]?[^)]*\)", source):
        # capture the binding name on the same logical line if possible
        line_start = source.rfind("\n", 0, m.start()) + 1
        line = source[line_start:m.end()]
        name_m = re.search(r"(?:const|let|var)\s+(\w+)\s*=", line)
        if name_m:
            matches.append(name_m.group(1))
    return matches


def test_pitfall_72_vue_number_input_string_ref_detected():
    bad_vue = """
    <script setup>
    const a = ref<string>('')
    </script>
    <template>
      <input type="number" v-model="a" />
    </template>
    """
    assert detect_input_number_string_state(bad_vue) == ["a"]


def test_pitfall_72_vue_number_input_number_ref_passes():
    good_vue = """
    <script setup>
    const a = ref<number | null>(null)
    </script>
    <template>
      <input type="number" v-model.number="a" />
    </template>
    """
    assert detect_input_number_string_state(good_vue) == []


# ---------------------------------------------------------------------------
# 7.3 JMustache rejects null keys in strict mode
# ---------------------------------------------------------------------------

def detect_mustache_null_attr(java_source: str) -> list[str]:
    """Return attribute names passed to model.addAttribute(name, null)."""
    return re.findall(
        r'addAttribute\(\s*"([^"]+)"\s*,\s*null\s*\)',
        java_source,
    )


def test_pitfall_73_mustache_null_addattribute_detected():
    bad = '''
    model.addAttribute("result", null);
    model.addAttribute("error", null);
    '''
    assert detect_mustache_null_attr(bad) == ["result", "error"]


def test_pitfall_73_mustache_empty_string_addattribute_passes():
    good = '''
    model.addAttribute("result", "");
    model.addAttribute("hasError", false);
    '''
    assert detect_mustache_null_attr(good) == []


# ---------------------------------------------------------------------------
# 7.4 pydantic-core no-wheel on Python ≥ 3.13 — pin pydantic >= 2.11
# ---------------------------------------------------------------------------

def detect_pydantic_pin_unsafe(requirements_txt: str, py_version: tuple[int, int]) -> bool:
    """Return True if Python ≥ 3.13 with pydantic pinned < 2.11 (unsafe wheel)."""
    if py_version < (3, 13):
        return False
    # Match e.g. "pydantic==2.10.3", "pydantic>=2.10,<2.11", "pydantic~=2.10"
    pin = re.search(r"^pydantic([=<>~!]+)(\d+)\.(\d+)", requirements_txt, re.M)
    if not pin:
        return False
    op, major, minor = pin.group(1), int(pin.group(2)), int(pin.group(3))
    return major == 2 and minor < 11


def test_pitfall_74_pydantic_old_pin_py314_detected():
    assert detect_pydantic_pin_unsafe("pydantic==2.10.3", (3, 14)) is True
    assert detect_pydantic_pin_unsafe("pydantic>=2.10,<2.11", (3, 14)) is True


def test_pitfall_74_pydantic_safe_pin_py314_passes():
    assert detect_pydantic_pin_unsafe("pydantic>=2.11", (3, 14)) is False
    assert detect_pydantic_pin_unsafe("pydantic==2.11.0", (3, 14)) is False


def test_pitfall_74_pydantic_old_pin_py312_lts_passes():
    assert detect_pydantic_pin_unsafe("pydantic==2.10.3", (3, 12)) is False


# ---------------------------------------------------------------------------
# 7.5 bUnit .Change() vs @bind:event="oninput" mismatch
# ---------------------------------------------------------------------------

def detect_bunit_change_oninput_mismatch(razor: str, test_csharp: str) -> bool:
    """Component uses @bind:event="oninput" but test uses .Change()."""
    component_oninput = '@bind:event="oninput"' in razor or "@bind:event='oninput'" in razor
    test_change = re.search(r'\.Change\(\s*"', test_csharp) is not None
    return component_oninput and test_change


def test_pitfall_75_bunit_change_with_oninput_detected():
    razor = '<input @bind="A" @bind:event="oninput" />'
    test = 'cut.Find("input").Change("5");'
    assert detect_bunit_change_oninput_mismatch(razor, test) is True


def test_pitfall_75_bunit_input_with_oninput_passes():
    razor = '<input @bind="A" @bind:event="oninput" />'
    test = 'cut.Find("input").Input("5");'
    assert detect_bunit_change_oninput_mismatch(razor, test) is False


def test_pitfall_75_bunit_change_with_onchange_passes():
    razor = '<input @bind="A" />'  # default = onchange
    test = 'cut.Find("input").Change("5");'
    assert detect_bunit_change_oninput_mismatch(razor, test) is False
