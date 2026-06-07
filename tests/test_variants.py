from __future__ import annotations

import pytest
from variants import (
    APEX_MODES_BY_KIND,
    get_variant,
    poc_script_path,
    resolve_poc_dir,
)


def test_get_variant_normalizes_iis_alias() -> None:
    spec = get_variant("microsoft-iis")
    assert spec.id == "iis"


def test_get_variant_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown variant"):
        get_variant("not-a-stack")


@pytest.mark.parametrize(
    "variant_id",
    ["nginx", "pingora", "httpd", "envoy", "iis"],
)
def test_vendor_poc_paths_exist(variant_id: str) -> None:
    poc_dir = resolve_poc_dir(variant_id)
    script = poc_script_path(variant_id)
    assert poc_dir.is_dir(), f"missing poc dir for {variant_id}"
    assert script.is_file(), f"missing script for {variant_id}"


def test_apex_modes_cover_all_kinds() -> None:
    for variant_id in ("nginx", "httpd", "iis"):
        spec = get_variant(variant_id)
        assert spec.kind in APEX_MODES_BY_KIND
        assert APEX_MODES_BY_KIND[spec.kind]
