"""Build the single-file router inspector (inline JS/CSS, data embedded, no network).

The page template lives in ``template.html``. The export (see :mod:`horizon.viz.export`) is
embedded either as gzip + base64 (decoded in the browser with ``DecompressionStream``; default)
or as plain JSON in a ``<script type="application/json">`` element.
"""

from __future__ import annotations

import base64
import gzip
import html
import json
import re
from pathlib import Path

from horizon.viz.export import load_export, validate_export

__all__ = ["build_html", "write_inspector"]

_TEMPLATE = Path(__file__).with_name("template.html")
_CONTENT = Path(__file__).with_name("content")
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _facts(data: dict) -> dict[str, str]:
    """Flat ``dotted.key -> text`` facts from ``meta`` and ``meta.params`` (nested dicts joined)."""
    meta = data["meta"]
    facts = {"duration_d": f"{meta['duration_s'] / 86400.0:g}",
             "p_rated_kw": f"{meta['p_rated_kw']:g}",
             "hold_speed_ms": f"{meta['hold_speed_ms']:g}"}

    def walk(prefix: str, obj) -> None:
        for k, v in obj.items():
            key = f"{prefix}{k}"
            if isinstance(v, dict):
                walk(key + ".", v)
            else:
                facts[key] = f"{v:g}" if isinstance(v, float) else str(v)

    walk("", meta.get("params") or {})
    return facts


def _fill(obj, facts: dict[str, str]):
    """Replace ``{{key}}`` placeholders in all strings of ``obj`` (unknown keys become ``n/a``)."""
    if isinstance(obj, str):
        return _PLACEHOLDER.sub(lambda m: facts.get(m.group(1), "n/a"), obj)
    if isinstance(obj, list):
        return [_fill(v, facts) for v in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, facts) for k, v in obj.items()}
    return obj


def load_content(data: dict) -> dict:
    """Guide texts (``guide_<lang>.md``) and glossary with placeholders filled from the export."""
    facts = _facts(data)
    out = {"guide": {}, **_fill(json.loads((_CONTENT / "glossary.json").read_text("utf-8")), facts)}
    for lang in ("en", "fr"):
        out["guide"][lang] = _fill((_CONTENT / f"guide_{lang}.md").read_text("utf-8"), facts)
    return out


def build_html(data: dict, gzip_data: bool = True) -> str:
    """Render the inspector page for an export dict.

    Parameters
    ----------
    data : dict  Export produced by :func:`horizon.viz.export.export_backtest`.
    gzip_data : bool  Embed as gzip + base64 (smaller; needs ``DecompressionStream``, available
        in current Chrome/Edge/Firefox/Safari) or as plain JSON.

    Returns
    -------
    str
        Complete HTML document.
    """
    validate_export(data)
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    if gzip_data:
        payload = base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode("ascii")
        tag = f'<script id="hz-data" type="application/octet-stream" data-enc="gzip-base64">' \
              f"{payload}</script>"
    else:
        safe = raw.decode().replace("<", "\\u003c")
        tag = f'<script id="hz-data" type="application/json" data-enc="json">{safe}</script>'
    content = json.dumps(load_content(data), separators=(",", ":"), ensure_ascii=False)
    tag += ('<script id="hz-content" type="application/json">'
            + content.replace("<", "\\u003c") + "</script>")
    page = _TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("<!--__TITLE__-->", html.escape(data["title"]))
    return page.replace("<!--__DATA__-->", tag)


def write_inspector(results: str | Path | dict, out: str | Path, gzip_data: bool = True) -> Path:
    """Write the inspector HTML.

    Parameters
    ----------
    results : path or dict  An export file (``.json`` / ``.json.gz``) or the export dict.
    out : path  Output ``.html``.
    gzip_data : bool  See :func:`build_html`.
    """
    data = results if isinstance(results, dict) else load_export(results)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(data, gzip_data), encoding="utf-8")
    return out
