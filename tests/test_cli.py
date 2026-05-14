from pathlib import Path

import pytest

from duplicates.__main__ import (
    _count,
    _dup_sort,
    _natural_key,
    _path_sort,
    main,
)
from duplicates.dupfinder import FileEntry


def _entry(path: Path, age: float = 0.0, size: int = 0) -> FileEntry:
    return FileEntry(path=path, size=size, age=age)


class TestNaturalKey:
    def test_digits_compare_as_integers(self) -> None:
        assert _natural_key("file2") < _natural_key("file10")

    def test_case_insensitive(self) -> None:
        assert _natural_key("Foo") == _natural_key("foo")

    def test_path_input(self) -> None:
        assert _natural_key(Path("dir/file2")) < _natural_key(Path("dir/file10"))

    def test_pure_digit_path(self) -> None:
        # No regression for paths that start with digits.
        assert _natural_key("1") < _natural_key("2") < _natural_key("10")


class TestSorting:
    def test_path_sort_uses_natural_order(self, tmp_path: Path) -> None:
        items = [
            _entry(tmp_path / "file10"),
            _entry(tmp_path / "file2"),
            _entry(tmp_path / "file1"),
        ]
        sorted_items = _path_sort(items)
        assert [e.path.name for e in sorted_items] == ["file1", "file2", "file10"]

    def test_dup_sort_oldest_first(self, tmp_path: Path) -> None:
        items = [
            _entry(tmp_path / "new", age=200.0),
            _entry(tmp_path / "old", age=100.0),
            _entry(tmp_path / "mid", age=150.0),
        ]
        sorted_items = _dup_sort(items)
        assert [e.path.name for e in sorted_items] == ["old", "mid", "new"]

    def test_dup_sort_breaks_age_ties_by_natural_path(self, tmp_path: Path) -> None:
        items = [
            _entry(tmp_path / "file10", age=100.0),
            _entry(tmp_path / "file2", age=100.0),
        ]
        sorted_items = _dup_sort(items)
        assert [e.path.name for e in sorted_items] == ["file2", "file10"]


class TestCount:
    def test_singular(self) -> None:
        assert _count(1, "file", "files") == "1 file"

    def test_plural(self) -> None:
        assert _count(0, "file", "files") == "0 files"
        assert _count(2, "file", "files") == "2 files"


@pytest.fixture
def dup_tree(tmp_path: Path) -> Path:
    # Files are created in alphabetical order; ctime progression plus the
    # natural-path tiebreaker make 'a.txt' the original of the (a, b) duplicate
    # pair regardless of clock resolution.
    (tmp_path / "a.txt").write_bytes(b"same")
    (tmp_path / "b.txt").write_bytes(b"same")
    (tmp_path / "c.txt").write_bytes(b"unique")
    return tmp_path


class TestMain:
    def test_default_output_lists_original_then_duplicates(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.argv", ["duplicates", str(dup_tree)])
        main()
        out = capsys.readouterr().out.splitlines()

        assert out[0] == str(dup_tree / "a.txt")
        assert out[1] == f"\t{dup_tree / 'b.txt'}"
        # 'c.txt' is unique and must not appear in default mode.
        assert not any("c.txt" in line for line in out)

    def test_dups_only_emits_nul_separated(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.argv", ["duplicates", "--dups-only", str(dup_tree)])
        main()
        out = capsys.readouterr().out

        # One group → one line, NUL between paths, no original printed.
        assert out.endswith("\n")
        line = out.rstrip("\n")
        items = line.split("\0")
        assert items == [str(dup_tree / "b.txt")]

    def test_unique_flag_prints_uniques(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.argv", ["duplicates", "--unique", str(dup_tree)])
        main()
        out = capsys.readouterr().out

        assert str(dup_tree / "c.txt") in out
        assert str(dup_tree / "a.txt") in out
        assert str(dup_tree / "b.txt") in out

    def test_summary_goes_to_stderr(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("sys.argv", ["duplicates", "--summary", str(dup_tree)])
        main()
        captured = capsys.readouterr()

        assert "SUMMARY:" in captured.err
        assert "3 files total" in captured.err
        assert "1 duplicate" in captured.err
