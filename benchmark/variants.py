"""Server variant registry for benchmark harness."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PLUGIN = Path(__file__).resolve().parent.parent
POC_ROOT = PLUGIN / "vendor" / "califio-publications" / "MADBugs" / "http2-bomb"
ALT_ROOT = PLUGIN / "poc"

VariantKind = Literal["nginx", "cookie", "iis"]
VariantId = Literal["nginx", "pingora", "httpd", "envoy", "iis"]

APEX_MODES_BY_KIND: dict[VariantKind, list[str]] = {
    "nginx": ["apex", "apex_scaled", "apex_mp", "churn", "optimized_oom", "pipelined_sustain"],
    "cookie": ["apex_cookie", "apex_cookie_scaled", "apex_cookie_mp"],
    "iis": ["apex_iis_mp"],
}


@dataclass(frozen=True)
class VariantSpec:
    id: str
    kind: VariantKind
    poc_subdir: str
    default_port: int
    amplification: str
    script_name: str = "hpack_bomb.py"

    def resolve_poc_dir(self) -> Path:
        primary = POC_ROOT / self.poc_subdir
        if self.kind == "nginx":
            if (primary / "hpack_bomb.py").is_file():
                return primary
            alt = ALT_ROOT / "nginx"
            if (alt / "hpack_bomb.py").is_file():
                return alt
        elif self.kind == "cookie":
            script = self.script_name
            if (primary / script).is_file():
                return primary
        elif self.kind == "iis":
            alt = primary / "poc"
            if (alt / self.script_name).is_file():
                return alt
            if (primary / self.script_name).is_file():
                return primary
        return primary


VARIANTS: dict[str, VariantSpec] = {
    "nginx": VariantSpec("nginx", "nginx", "nginx", 443, "~70:1"),
    "pingora": VariantSpec("pingora", "nginx", "pingora/attacker", 443, "~62:1"),
    "httpd": VariantSpec(
        "httpd", "cookie", "httpd", 10080, "~4,000:1",
        script_name="hpack_httpd_cookie_bomb.py",
    ),
    "envoy": VariantSpec(
        "envoy", "cookie", "envoy", 10000, "~5,700:1",
        script_name="hpack_cookie_bomb.py",
    ),
    "iis": VariantSpec(
        "iis", "iis", "microsoft-iis", 443, "~68:1",
        script_name="iis_hpack_dos.py",
    ),
}


def _normalize_variant_id(variant_id: str) -> str:
    vid = variant_id.strip().lower()
    if vid in ("microsoft-iis", "microsoft_iis"):
        return "iis"
    return vid


def get_variant(variant_id: str) -> VariantSpec:
    vid = _normalize_variant_id(variant_id)
    if vid not in VARIANTS:
        raise ValueError(f"Unknown variant '{variant_id}'. Choose: {', '.join(VARIANTS)}")
    return VARIANTS[vid]


def resolve_poc_dir(variant_id: str) -> Path:
    return get_variant(variant_id).resolve_poc_dir()


def poc_script_path(variant_id: str) -> Path:
    spec = get_variant(variant_id)
    return spec.resolve_poc_dir() / spec.script_name


def set_poc_path(variant_id: str) -> Path:
    """Insert variant POC dir on sys.path; return resolved directory."""
    poc_dir = resolve_poc_dir(variant_id)
    poc_str = str(poc_dir.resolve())
    while poc_str in sys.path:
        sys.path.remove(poc_str)
    sys.path.insert(0, poc_str)
    return poc_dir


def default_port_for(variant_id: str) -> int:
    return get_variant(variant_id).default_port


def apex_modes_for_variant(variant_id: str) -> list[str]:
    spec = get_variant(variant_id)
    return list(APEX_MODES_BY_KIND[spec.kind])


def get_active_variant() -> str:
    return "nginx"
