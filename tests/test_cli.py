import json
import re
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
        # Elapsed time is part of the summary now.
        assert re.search(r"in \d+\.\d{4}s", captured.err)


class TestJsonOutput:
    def _run_json(
        self,
        argv: list[str],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict:
        monkeypatch.setattr("sys.argv", argv)
        main()
        out = capsys.readouterr().out
        return json.loads(out)

    def test_basic_shape(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data = self._run_json(
            ["duplicates", "--json", str(dup_tree)], capsys, monkeypatch
        )

        assert data["scanned_paths"] == [str(dup_tree)]
        assert len(data["duplicates"]) == 1
        group = data["duplicates"][0]
        assert group["size"] == len(b"same")
        assert group["hash"].startswith("sha256:")
        assert len(group["hash"]) == len("sha256:") + 64
        paths = [f["path"] for f in group["files"]]
        assert set(paths) == {str(dup_tree / "a.txt"), str(dup_tree / "b.txt")}
        # Oldest first.
        assert paths[0] == str(dup_tree / "a.txt")

    def test_statistics_counts_match(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data = self._run_json(
            ["duplicates", "--json", str(dup_tree)], capsys, monkeypatch
        )
        stats = data["statistics"]

        assert stats["total_files"] == 3
        assert stats["unique_files"] == 1
        assert stats["duplicate_groups"] == 1
        assert stats["duplicate_copies"] == 1
        assert stats["unreadable_files"] == 0
        assert isinstance(stats["elapsed_seconds"], (int, float))
        assert stats["elapsed_seconds"] >= 0

    def test_unique_block_omitted_by_default(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data = self._run_json(
            ["duplicates", "--json", str(dup_tree)], capsys, monkeypatch
        )
        assert "unique" not in data

    def test_unique_block_present_with_flag(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data = self._run_json(
            ["duplicates", "--json", "--unique", str(dup_tree)],
            capsys,
            monkeypatch,
        )
        assert len(data["unique"]) == 1
        assert data["unique"][0]["path"] == str(dup_tree / "c.txt")

    def test_unreadable_block_omitted_when_empty(
        self,
        dup_tree: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        data = self._run_json(
            ["duplicates", "--json", str(dup_tree)], capsys, monkeypatch
        )
        assert "unreadable" not in data

    @pytest.mark.parametrize(
        "extra",
        [
            ["--dups-only"],
            ["--summary"],
        ],
    )
    def test_json_mutually_exclusive_with_other_output_modes(
        self,
        dup_tree: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        extra: list[str],
    ) -> None:
        monkeypatch.setattr("sys.argv", ["duplicates", "--json", *extra, str(dup_tree)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        assert "not allowed with argument" in capsys.readouterr().err

    def test_dups_only_and_summary_mutually_exclusive(
        self,
        dup_tree: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            "sys.argv",
            ["duplicates", "--dups-only", "--summary", str(dup_tree)],
        )
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
