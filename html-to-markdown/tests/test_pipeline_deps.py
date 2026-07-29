"""Tests for pipeline runtime-dependency preflight (改进1).

Loads pipeline module by path (skill dir is not a package).
Run: python3 tests/test_pipeline_deps.py   (from skill dir)
"""
import importlib.util
import sys
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("h2m_pipeline", _SKILL / "pipeline.py")
_pl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _pl  # dataclasses need the module registered
_spec.loader.exec_module(_pl)

check = _pl._check_runtime_deps


def test_missing_numpy_is_reported():
    # 假 dep map:一个真存在(json 一定在),一个不存在
    err = check({"json": "json", "definitely_not_a_real_module_xyz": "ghost-dist"})
    assert err is not None
    assert "ghost-dist" in err  # 报的是发行名,不是 import 名


def test_hint_includes_uv_command():
    err = check({"definitely_not_a_real_module_xyz": "ghost-dist"})
    assert err is not None
    assert "uv" in err
    assert "requirements.txt" in err


def test_all_present_returns_none():
    # 全用 stdlib 名,必存在 → None
    assert check({"json": "json", "pathlib": "pathlib", "re": "re"}) is None


def test_default_deps_map_uses_import_names_as_keys():
    # 默认 map 的 key 是 import 名(bs4/PIL/cv2),value 是发行名
    m = _pl._RUNTIME_DEPS
    assert m["bs4"] == "beautifulsoup4"
    assert m["PIL"] == "pillow"
    assert m["cv2"] == "opencv-python-headless"


def test_reports_multiple_missing_sorted():
    err = check({"zzz_ghost": "z-dist", "aaa_ghost": "a-dist"})
    # 排序后 a-dist 在 z-dist 前
    assert err.index("a-dist") < err.index("z-dist")


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e!r}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
