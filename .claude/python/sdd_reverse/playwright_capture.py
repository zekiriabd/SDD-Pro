"""SDD_Pro Reverse Engineering Phase 4 — Playwright capture (library).

Captures the runtime-rendered HTML + computed CSS palette of a single legacy
route via headless Chromium (Playwright).

The Playwright API is wrapped behind `_capture_via_playwright_async()` which is
injectable for tests. The library can be loaded and most logic exercised even
when `playwright` is NOT installed — only the actual `capture_url()` call
requires Playwright at runtime.

Outputs persisted to disk:
- {output_dir}/{unit_id}.html      (raw outerHTML post-JS)
- {output_dir}/{unit_id}-palette.json   (computed colors, fonts, spacings)
- {output_dir}/{unit_id}.png       (optional screenshot)

Error class prefixes (cf. rules/reverse-engineering.md):
- [REVERSE_UI_PLAYWRIGHT_MISSING] : Python `playwright` package or Chromium absent
- [REVERSE_UI_CAPTURE_EMPTY]      : outerHTML < 500 chars (page error or redirect)
- [REVERSE_UI_AUTH_REQUIRED]      : capture returned 401/403
- [REVERSE_UI_CAPTURE_FAILED]     : Playwright timeout, navigation error, crash
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# JavaScript snippet evaluated in the page to extract a palette of computed
# styles. Returns a structured dict.
EXTRACT_PALETTE_JS = """
() => {
    const allEls = document.querySelectorAll('*');
    const colors = new Set();
    const bgs = new Set();
    const fonts = new Set();
    const spacings = new Set();
    const fontSizes = new Set();
    let elementCount = 0;
    allEls.forEach(el => {
      elementCount++;
      const cs = getComputedStyle(el);
      if (cs.color && cs.color !== 'rgba(0, 0, 0, 0)') colors.add(cs.color);
      if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)') bgs.add(cs.backgroundColor);
      if (cs.fontFamily) fonts.add(cs.fontFamily);
      if (cs.padding && cs.padding !== '0px') spacings.add(cs.padding);
      if (cs.margin && cs.margin !== '0px') spacings.add(cs.margin);
      if (cs.fontSize) fontSizes.add(cs.fontSize);
    });
    return {
      colors: [...colors],
      backgrounds: [...bgs],
      fonts: [...fonts],
      spacings: [...spacings].slice(0, 20),
      fontSizes: [...fontSizes].slice(0, 12),
      elementCount: elementCount,
    };
}
"""


# ------------------------------------------------------------- data types


@dataclass
class CaptureCookie:
    """Cookie spec injected before navigation, compatible Playwright API."""

    name: str
    value: str
    domain: str = "127.0.0.1"
    path: str = "/"


@dataclass
class CaptureError:
    """Structured error with [REVERSE_UI_*] class prefix."""

    code: str
    detail: str
    fix: str = ""


@dataclass
class CaptureResult:
    """Outcome of capture_url(). Persisted to disk by caller if ok=True."""

    ok: bool
    unit_id: str = ""
    url: str = ""
    raw_html: str = ""
    palette: dict[str, Any] = field(default_factory=dict)
    screenshot_bytes: bytes = b""
    html_size: int = 0
    status_code: int | None = None
    errors: list[CaptureError] = field(default_factory=list)
    warnings: list[CaptureError] = field(default_factory=list)


# ------------------------------------------------------- dependency check


def is_playwright_available() -> bool:
    """Return True iff the `playwright` Python package is importable.

    Note : this does NOT verify Chromium is downloaded. That check requires
    actually calling `chromium.launch()` and catching the resulting error.
    """
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def playwright_install_hint() -> str:
    """Return a human-readable FIX for [REVERSE_UI_PLAYWRIGHT_MISSING]."""
    return (
        "Install Playwright: pip install playwright && "
        "python -m playwright install chromium"
    )


# ------------------------------------------------------- HTML size check


# Minimum outerHTML size for a capture to count as substantive.
# Empty pages, redirects, and error pages typically yield < 500 chars.
MIN_HTML_SIZE_CHARS = 500


def assess_capture_size(raw_html: str) -> CaptureError | None:
    """Return a CaptureError if html is too small, else None.

    Threshold MIN_HTML_SIZE_CHARS = 500 chars.
    """
    if len(raw_html) < MIN_HTML_SIZE_CHARS:
        return CaptureError(
            code="REVERSE_UI_CAPTURE_EMPTY",
            detail=(
                f"outerHTML size {len(raw_html)} < {MIN_HTML_SIZE_CHARS} chars "
                "(page error, redirect, or empty body)"
            ),
            fix=(
                "verify the legacy serves a substantive response at this URL ; "
                "check legacy stderr ; consider auth-cookies.json"
            ),
        )
    return None


# -------------------------------------------------------- HTTP status check


def assess_status_code(status: int | None) -> CaptureError | None:
    """Return a CaptureError if status indicates auth-required, else None.

    Treats 401/403 as auth-required ; other 4xx and 5xx are logged but not
    blocking (the caller decides via raw_html assessment).
    """
    if status in (401, 403):
        return CaptureError(
            code="REVERSE_UI_AUTH_REQUIRED",
            detail=f"HTTP {status} returned by legacy — page protected",
            fix=(
                "provide pre-authenticated cookies in "
                "workspace/old/{P}/.sys/auth-cookies.json (cf. design doc §10)"
            ),
        )
    return None


# ---------------------------------------------------- Playwright wrapper


async def _capture_via_playwright_async(
    base_url: str,
    route: str,
    *,
    viewport_w: int = 1280,
    viewport_h: int = 800,
    wait_network_idle_s: int = 30,
    auth_cookies: list[CaptureCookie] | None = None,
    take_screenshot: bool = True,
) -> dict[str, Any]:
    """Drive Playwright Chromium headless to capture a single URL.

    Returns a dict with keys: raw_html (str), palette (dict), screenshot_bytes (bytes),
    status_code (int | None). Raises if Playwright unavailable or navigation fails.

    Pure-async function — tests mock the entire body via _capture_fn injection
    in capture_url(). Not invoked in unit tests.
    """
    # Local import : module must remain loadable when Playwright is absent.
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]

    full_url = f"{base_url.rstrip('/')}{route if route.startswith('/') else '/' + route}"
    status_code: int | None = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h},
                user_agent="SDDPro-Reverse-Capture/1.0",
            )
            if auth_cookies:
                # Playwright cookie spec is dict-of-str
                await ctx.add_cookies(
                    [
                        {
                            "name": c.name,
                            "value": c.value,
                            "domain": c.domain,
                            "path": c.path,
                        }
                        for c in auth_cookies
                    ]
                )
            page = await ctx.new_page()

            def _on_response(response):
                nonlocal status_code
                # Capture main document response only
                if response.url == full_url or response.url.rstrip("/") == full_url.rstrip("/"):
                    status_code = response.status

            page.on("response", _on_response)

            await page.goto(
                full_url,
                wait_until="networkidle",
                timeout=wait_network_idle_s * 1000,
            )
            raw_html: str = await page.content()
            palette: dict[str, Any] = await page.evaluate(EXTRACT_PALETTE_JS)

            screenshot_bytes = b""
            if take_screenshot:
                screenshot_bytes = await page.screenshot(full_page=True)

            return {
                "raw_html": raw_html,
                "palette": palette,
                "screenshot_bytes": screenshot_bytes,
                "status_code": status_code,
            }
        finally:
            await browser.close()


# ------------------------------------------------------------- main entry


def capture_url(
    base_url: str,
    route: str,
    unit_id: str,
    *,
    auth_cookies: list[CaptureCookie] | None = None,
    take_screenshot: bool = True,
    wait_network_idle_s: int = 30,
    _capture_fn: Any = None,  # injected for tests : async callable
    _is_available_fn: Any = None,  # injected for tests
    _asyncio_run: Any = None,  # injected for tests
) -> CaptureResult:
    """Capture a single URL via Playwright, return structured CaptureResult.

    Never raises — failures encoded in result.errors.

    Args:
        base_url:           e.g. "http://127.0.0.1:5099"
        route:              e.g. "/Default.aspx"
        unit_id:            e.g. "unit-001" — used only for tagging the result
        auth_cookies:       optional pre-auth cookies
        take_screenshot:    True to also capture a full-page PNG
        wait_network_idle_s: networkidle timeout (default 30s)

    Test injection points:
        _capture_fn         async callable replacing _capture_via_playwright_async
                            Receives the same kwargs ; must return a dict with
                            keys raw_html, palette, screenshot_bytes, status_code.
        _is_available_fn    callable returning bool (overrides is_playwright_available)
        _asyncio_run        callable equivalent to asyncio.run (lets tests skip
                            the event loop entirely)
    """
    avail_fn = _is_available_fn if _is_available_fn is not None else is_playwright_available
    if not avail_fn():
        return CaptureResult(
            ok=False,
            unit_id=unit_id,
            url=f"{base_url}{route}",
            errors=[
                CaptureError(
                    code="REVERSE_UI_PLAYWRIGHT_MISSING",
                    detail="Python package 'playwright' not importable",
                    fix=playwright_install_hint(),
                )
            ],
        )

    capture_fn = _capture_fn if _capture_fn is not None else _capture_via_playwright_async

    try:
        if _asyncio_run is not None:
            captured = _asyncio_run(
                capture_fn(
                    base_url=base_url,
                    route=route,
                    auth_cookies=auth_cookies,
                    take_screenshot=take_screenshot,
                    wait_network_idle_s=wait_network_idle_s,
                )
            )
        else:
            import asyncio
            captured = asyncio.run(
                capture_fn(
                    base_url=base_url,
                    route=route,
                    auth_cookies=auth_cookies,
                    take_screenshot=take_screenshot,
                    wait_network_idle_s=wait_network_idle_s,
                )
            )
    except Exception as exc:  # noqa: BLE001 - Playwright errors are diverse
        return CaptureResult(
            ok=False,
            unit_id=unit_id,
            url=f"{base_url}{route}",
            errors=[
                CaptureError(
                    code="REVERSE_UI_CAPTURE_FAILED",
                    detail=f"{type(exc).__name__}: {exc}",
                    fix=(
                        "check legacy is still running ; verify route exists ; "
                        "increase wait_network_idle_s ; check Chromium install "
                        f"(`python -m playwright install chromium`)"
                    ),
                )
            ],
        )

    raw_html: str = captured.get("raw_html", "")
    palette: dict[str, Any] = captured.get("palette", {})
    screenshot_bytes: bytes = captured.get("screenshot_bytes", b"")
    status_code = captured.get("status_code")

    result = CaptureResult(
        ok=True,
        unit_id=unit_id,
        url=f"{base_url}{route}",
        raw_html=raw_html,
        palette=palette,
        screenshot_bytes=screenshot_bytes,
        html_size=len(raw_html),
        status_code=status_code,
    )

    # Post-capture quality checks : may downgrade to warnings or errors
    size_err = assess_capture_size(raw_html)
    if size_err is not None:
        result.ok = False
        result.errors.append(size_err)

    auth_err = assess_status_code(status_code)
    if auth_err is not None:
        # Auth-required is a WARNING by default : the capture may still have
        # partial content (login form). Caller decides via result.warnings.
        result.warnings.append(auth_err)

    return result


# ------------------------------------------------------- persistence


def write_capture_outputs(
    result: CaptureResult,
    output_dir: Path,
    *,
    write_screenshot: bool = True,
) -> dict[str, str]:
    """Persist capture artifacts to disk atomically.

    Writes :
      - {output_dir}/{unit_id}.html
      - {output_dir}/{unit_id}-palette.json
      - {output_dir}/{unit_id}.png  (if write_screenshot and bytes present)

    Returns a dict {key: path-as-string} for the caller's JSON output.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / f"{result.unit_id}.html"
    palette_path = output_dir / f"{result.unit_id}-palette.json"

    _atomic_write_text(html_path, result.raw_html)
    _atomic_write_text(
        palette_path,
        json.dumps(result.palette, indent=2, ensure_ascii=False),
    )

    written = {"html": str(html_path), "palette": str(palette_path)}

    if write_screenshot and result.screenshot_bytes:
        screenshot_path = output_dir / f"{result.unit_id}.png"
        _atomic_write_bytes(screenshot_path, result.screenshot_bytes)
        written["screenshot"] = str(screenshot_path)

    return written


def _atomic_write_text(target: Path, content: str) -> None:
    """Atomic write via .sddtmp + rename. Idempotent on the target path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".sddtmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


def _atomic_write_bytes(target: Path, content: bytes) -> None:
    """Atomic write of binary content."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".sddtmp")
    tmp.write_bytes(content)
    tmp.replace(target)


# --------------------------------------------------- auth cookies loader


def load_auth_cookies(cookies_file: Path) -> list[CaptureCookie]:
    """Load pre-auth cookies from {project}/.sys/auth-cookies.json.

    Returns [] if file absent (not an error). Raises ValueError if schema bad.
    Format per design doc §10 :
        { "version": 1, "cookies": [ {"name", "value", "domain", "path"}, ... ] }
    """
    if not cookies_file.is_file():
        return []

    raw = json.loads(cookies_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "cookies" not in raw:
        raise ValueError(f"auth-cookies.json must have a top-level 'cookies' key")

    if raw.get("version") != 1:
        raise ValueError(
            f"auth-cookies.json version {raw.get('version')!r} unsupported (expected 1)"
        )

    cookies_data = raw["cookies"]
    if not isinstance(cookies_data, list):
        raise ValueError("auth-cookies.json 'cookies' must be a list")

    out: list[CaptureCookie] = []
    for c in cookies_data:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            raise ValueError(f"invalid cookie entry: {c!r}")
        out.append(
            CaptureCookie(
                name=c["name"],
                value=c["value"],
                domain=c.get("domain", "127.0.0.1"),
                path=c.get("path", "/"),
            )
        )
    return out


# -------------------------------------------------- route derivation


def derive_route_from_unit_path(page_path: str) -> str:
    """Translate a unit's page_path (e.g. 'Customers/List.aspx') to an HTTP route.

    Conservative rules :
    - Always prefix with '/'
    - Preserve the extension (.aspx, .jsp, .php, .cshtml) — legacy servers
      usually serve these directly. The agent in Sprint 4 can override per stack.
    - Replace OS-specific separators with '/'
    """
    if not page_path:
        return "/"
    cleaned = page_path.replace("\\", "/").strip("/")
    return "/" + cleaned


def result_to_json_dict(result: CaptureResult) -> dict[str, Any]:
    """Convert CaptureResult to a JSON-serializable dict (screenshot_bytes stripped)."""
    return {
        "ok": result.ok,
        "unit_id": result.unit_id,
        "url": result.url,
        "html_size": result.html_size,
        "status_code": result.status_code,
        "palette": result.palette,
        "errors": [asdict(err) for err in result.errors],
        "warnings": [asdict(warn) for warn in result.warnings],
    }
