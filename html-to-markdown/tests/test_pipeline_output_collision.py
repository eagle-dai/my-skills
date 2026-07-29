"""Tests for output-dir multi-document collision detection (改进2).

Run: python3 tests/test_pipeline_output_collision.py   (from skill dir)
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_SKILL = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("h2m_pipeline", _SKILL / "pipeline.py")
_pl = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _pl
_spec.loader.exec_module(_pl)

detect = _pl.detect_output_collision


def _make_delivery(out: Path, name: str) -> None:
    """Simulate a delivered package: <name>/files/ subtree + <name>.zip."""
    (out / name / "files" / name).mkdir(parents=True, exist_ok=True)
    (out / name / f"{name}.md").write_text("x", encoding="utf-8")
    (out / f"{name}.zip").write_bytes(b"PK\x03\x04stub")


def test_different_name_is_a_collision():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        _make_delivery(out, "doc-A")
        assert detect(out, "doc-B") == ["doc-A"]


def test_same_name_is_not_a_collision():
    # resume 场景:同名重跑,绝不能报冲突
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        _make_delivery(out, "doc-A")
        assert detect(out, "doc-A") == []


def test_empty_dir_no_collision():
    with tempfile.TemporaryDirectory() as d:
        assert detect(Path(d), "doc-A") == []


def test_nonexistent_dir_no_collision():
    assert detect(Path("/no/such/dir/xyz"), "doc-A") == []


def test_multiple_others_sorted_and_deduped():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        _make_delivery(out, "zeta")
        _make_delivery(out, "alpha")
        # 当前 package 是第三个名字 → 两个都算 other,排序去重
        assert detect(out, "current") == ["alpha", "zeta"]


def test_preflight_dir_alone_is_not_a_package():
    # 反例:只有 preflight/ 没有 <name>/files/ 或 zip → 不算已交付文档
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        (out / "preflight").mkdir()
        (out / "formula-validation.html").write_text("x", encoding="utf-8")
        assert detect(out, "doc-A") == []


def test_bare_dir_without_files_subtree_ignored():
    # 反例:一个恰好同 output 的杂目录,没有 files/ 子树 → 不误报
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        (out / "random_dir").mkdir()
        assert detect(out, "doc-A") == []


def test_dir_with_files_but_no_md_not_flagged():
    # 反例:目录有 files/ 子树但无 <name>.md(如 preflight/ 恰好含 files/)
    # → 不是交付包,不误报(收紧判据后靠 <name>.md 标志)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        (out / "weird" / "files").mkdir(parents=True)
        assert detect(out, "doc-A") == []


def test_symlink_to_package_dir_not_flagged():
    # 反例:指向别处包目录的 symlink → 不当作本 output 的交付冲突
    import os

    with tempfile.TemporaryDirectory() as d:
        out = Path(d)
        real = out / "real-pkg"
        (real / "files").mkdir(parents=True)
        (real / "real-pkg.md").write_text("x", encoding="utf-8")
        # real-pkg 本身是合法异名包 → 会被报;但通过 symlink 别名不额外报
        link = out / "aliased"
        os.symlink(real, link)
        # 只应报真目录 real-pkg,symlink aliased 被 is_symlink 排除
        assert detect(out, "doc-A") == ["real-pkg"]


if __name__ == "__main__":
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
