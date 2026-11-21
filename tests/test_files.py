# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for publishing a set of files atomically, and for the guards around it."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import pytest

from faithful_core.errors import OutputError
from faithful_core.files import copy_new, refuse_aliases, write_files

if TYPE_CHECKING:
    from collections.abc import Callable

FILES = {"a.txt": b"first file\n" * 100, "b.txt": b"second file\n" * 100}
SLUG = "example"


class FlakyHandle:
    """A real file handle that fails at one chosen point."""

    def __init__(self, handle: IO[bytes], fail: str) -> None:
        self.handle = handle
        self.fail = fail

    def __enter__(self) -> FlakyHandle:
        """Enter like the real handle."""
        return self

    def __exit__(self, *_: object) -> None:
        """Close the real handle, then fail if asked to fail on close."""
        self.handle.close()
        if self.fail == "close":
            raise OSError(5, "Input/output error")

    def write(self, data: bytes) -> int:
        if self.fail == "write":
            self.handle.write(data[: len(data) // 2])
            self.handle.flush()
            raise OSError(28, "No space left on device")
        return self.handle.write(data)

    def flush(self) -> None:
        self.handle.flush()

    def fileno(self) -> int:
        return self.handle.fileno()


@pytest.fixture
def no_hard_links(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Make hard links unsupported; return a switch that injects one failure in the copy."""
    copying = {"on": False}
    fail = {"at": ""}
    real_fdopen = os.fdopen
    real_read = Path.read_bytes

    def no_links(*_: object) -> None:
        copying["on"] = True
        raise OSError(1, "Operation not permitted")

    def fdopen(fd: int, *args: Any, **kwargs: Any) -> object:
        if copying["on"] and fail["at"] == "fdopen":
            raise OSError(24, "Too many open files")
        handle = real_fdopen(fd, *args, **kwargs)
        return FlakyHandle(handle, fail["at"]) if copying["on"] else handle

    def read_bytes(self: Path) -> bytes:
        if copying["on"] and fail["at"] == "read":
            raise OSError(5, "Input/output error")
        return real_read(self)

    monkeypatch.setattr(os, "link", no_links)
    monkeypatch.setattr(os, "fdopen", fdopen)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    def inject(point: str) -> None:
        fail["at"] = point

    return inject


def test_copy_fallback_publishes_complete_private_files(
    tmp_path: Path, no_hard_links: Callable[[str], None]
) -> None:
    no_hard_links("")
    written = write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert [p.name for p in written] == list(FILES)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(FILES)
    for path in written:
        assert path.read_bytes() == FILES[path.name]
        if os.name == "posix":
            assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("point", ["read", "fdopen", "write", "close"])
def test_copy_fallback_failure_leaves_no_partial_file(
    tmp_path: Path, no_hard_links: Callable[[str], None], point: str
) -> None:
    """A read, partial write, or close failure removes the file the fallback created."""
    no_hard_links(point)
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert list(tmp_path.iterdir()) == []


def test_copy_fallback_never_removes_a_file_it_did_not_create(
    tmp_path: Path, no_hard_links: Callable[[str], None]
) -> None:
    """A name taken by someone else before the exclusive create is left alone."""
    no_hard_links("")
    real_open = os.open

    def racing_open(path: str, flags: int, mode: int = 0o777) -> int:
        if str(path).endswith("b.txt"):
            Path(path).write_text("someone else", encoding="utf-8")
        return real_open(path, flags, mode)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", racing_open)
        with pytest.raises(OutputError, match="appeared while writing"):
            write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert [p.name for p in tmp_path.iterdir()] == ["b.txt"]
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "someone else"


# Publishing with hard links, replacing, and refusing ----------------------------------


def test_files_are_written_unchanged_and_private(tmp_path: Path) -> None:
    out = tmp_path / "new" / "deeper"
    written = write_files(out, FILES, force=False, slug=SLUG)
    assert [p.name for p in written] == list(FILES)
    for path in written:
        assert path.read_bytes() == FILES[path.name]
        if os.name == "posix":
            assert path.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in out.iterdir()) == sorted(FILES)
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o700


def test_an_existing_file_is_refused_without_force_and_left_alone(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_bytes(b"mine")
    with pytest.raises(OutputError, match=r"b\.txt already exists; use --force"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert (tmp_path / "b.txt").read_bytes() == b"mine"
    assert [p.name for p in tmp_path.iterdir()] == ["b.txt"]


def test_several_existing_files_are_all_named(tmp_path: Path) -> None:
    for name in FILES:
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(OutputError, match="already exist; use --force"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)


def test_force_replaces_every_file_and_leaves_no_backup(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"old")
    write_files(tmp_path, FILES, force=True, slug=SLUG)
    assert (tmp_path / "a.txt").read_bytes() == FILES["a.txt"]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(FILES)
    if os.name == "posix":
        assert (tmp_path / "a.txt").stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="symbolic links need POSIX here")
@pytest.mark.parametrize("force", [False, True])
def test_a_symlink_at_a_target_is_never_followed(tmp_path: Path, *, force: bool) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"precious")
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").symlink_to(victim)
    if force:
        write_files(out, FILES, force=True, slug=SLUG)
        assert not (out / "a.txt").is_symlink()
        assert (out / "a.txt").read_bytes() == FILES["a.txt"]
    else:
        with pytest.raises(OutputError, match="already exists"):
            write_files(out, FILES, force=False, slug=SLUG)
        assert (out / "a.txt").is_symlink()
    assert victim.read_bytes() == b"precious"


@pytest.mark.skipif(os.name != "posix", reason="symbolic links need POSIX here")
def test_a_dangling_symlink_counts_as_existing(tmp_path: Path) -> None:
    (tmp_path / "a.txt").symlink_to(tmp_path / "nowhere")
    with pytest.raises(OutputError, match="already exists"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert not (tmp_path / "nowhere").exists()


def test_a_directory_at_a_target_is_refused_even_with_force(tmp_path: Path) -> None:
    (tmp_path / "a.txt").mkdir()
    with pytest.raises(OutputError, match="is a directory"):
        write_files(tmp_path, FILES, force=True, slug=SLUG)


def test_an_output_directory_that_cannot_be_made_is_reported(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_bytes(b"x")
    with pytest.raises(OutputError, match="cannot create"):
        write_files(blocker / "sub", FILES, force=False, slug=SLUG)


def test_a_failure_while_staging_leaves_the_directory_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync
    calls = {"n": 0}

    def fsync(fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(28, "No space left on device")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert list(tmp_path.iterdir()) == []


def test_a_forced_replace_that_fails_restores_the_old_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in FILES:
        (tmp_path / name).write_bytes(b"old " + name.encode())
    real_replace = Path.replace
    calls = {"n": 0}

    def replace(self: Path, target: Path) -> Path:
        calls["n"] += 1
        # two moves to backups, then the first new file in, then the second fails
        if calls["n"] == 4:
            raise OSError(5, "Input/output error")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=True, slug=SLUG)
    monkeypatch.undo()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == {
        name: b"old " + name.encode() for name in FILES
    }


def test_a_failed_backup_move_is_undone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.txt").write_bytes(b"old")
    real_replace = Path.replace

    def replace(self: Path, target: Path) -> Path:
        if self.name == "a.txt":
            raise OSError(13, "Permission denied")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=True, slug=SLUG)
    monkeypatch.undo()
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]
    assert (tmp_path / "a.txt").read_bytes() == b"old"


def test_a_failure_after_the_first_link_removes_the_placed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link
    calls = {"n": 0}

    def link(src: str | Path, dst: str | Path) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise PermissionError(13, "Permission denied")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(os, "open", lambda *_a, **_k: (_ for _ in ()).throw(OSError(13, "no")))
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert list(tmp_path.iterdir()) == []


def test_a_name_that_appears_during_linking_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def link(src: str | Path, dst: str | Path) -> None:
        if str(dst).endswith("b.txt"):
            Path(dst).write_bytes(b"someone else")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", link)
    with pytest.raises(OutputError, match="appeared while writing"):
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert [p.name for p in tmp_path.iterdir()] == ["b.txt"]


# Text and bytes, names, and removing the files of an earlier run -----------------------


def test_text_is_written_as_utf8_with_no_newline_translation(tmp_path: Path) -> None:
    write_files(tmp_path, {"t.txt": "café 中\r\nline\n", "b.bin": b"\x00\xff\r\n"},
                force=False, slug=SLUG)  # fmt: skip
    assert (tmp_path / "t.txt").read_bytes() == "café 中\r\nline\n".encode()
    assert (tmp_path / "b.bin").read_bytes() == b"\x00\xff\r\n"


def test_the_files_are_placed_in_the_order_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    placed: list[str] = []
    real_link = os.link

    def link(src: str | Path, dst: str | Path) -> None:
        placed.append(Path(dst).name)
        real_link(src, dst)

    monkeypatch.setattr(os, "link", link)
    names = ["z.txt", "m.txt", "a.json", "manifest.json"]
    write_files(tmp_path, dict.fromkeys(names, "x"), force=False, slug=SLUG)
    assert placed == names


@pytest.mark.parametrize("force", [False, True])
def test_temporary_files_are_named_for_the_slug_and_leave_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, force: bool
) -> None:
    (tmp_path / "a.txt").write_bytes(b"old")
    seen: set[str] = set()
    real_mkstemp = tempfile.mkstemp

    def mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)
        seen.add(Path(name).name)
        return fd, name

    monkeypatch.setattr(tempfile, "mkstemp", mkstemp)
    if force:
        write_files(tmp_path, FILES, force=True, slug="tool-x")
    else:
        write_files(tmp_path / "fresh", FILES, force=False, slug="tool-x")
    assert seen
    assert all(re.fullmatch(r"\.tool-x-(old-)?\w+\.(tmp|bak)", name) for name in seen), seen
    assert any(name.startswith(".tool-x-old-") for name in seen) is force
    leftovers = [p.name for p in tmp_path.rglob(".*") if p.is_file()]
    assert leftovers == []


@pytest.mark.parametrize("slug", ["", "-x", "a/b", "a b", "..", ".hidden", "a\\b", "ü"])
def test_a_slug_that_cannot_be_part_of_a_file_name_is_a_programming_error(
    tmp_path: Path, slug: str
) -> None:
    with pytest.raises(ValueError, match="cannot be used in a file name"):
        write_files(tmp_path, FILES, force=False, slug=slug)
    assert list(tmp_path.iterdir()) == []


def test_the_slug_is_required() -> None:
    with pytest.raises(TypeError, match="slug"):
        write_files(Path("unused"), FILES, force=False)  # type: ignore[call-arg]


def test_remove_deletes_the_files_of_an_earlier_run_with_force(tmp_path: Path) -> None:
    for name in ("a.txt", "old-1.txt", "old-2.txt", "unrelated.txt"):
        (tmp_path / name).write_bytes(b"old " + name.encode())
    written = write_files(
        tmp_path, FILES, force=True, slug=SLUG, remove=["old-1.txt", "old-2.txt", "a.txt", "gone"]
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt", "b.txt", "unrelated.txt"]
    assert (tmp_path / "a.txt").read_bytes() == FILES[
        "a.txt"
    ]  # a name in files is written, not removed
    assert [p.name for p in written] == list(FILES)


def test_remove_does_nothing_without_force_and_the_refusal_says_what_force_removes(
    tmp_path: Path,
) -> None:
    (tmp_path / "old.txt").write_bytes(b"old")
    (tmp_path / "a.txt").write_bytes(b"mine")
    with pytest.raises(
        OutputError, match=r"a\.txt already exists; use --force to replace it, or"
    ) as e:
        write_files(tmp_path, FILES, force=False, slug=SLUG, remove=["old.txt"])
    assert "--force also removes files an earlier run wrote" in str(e.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt", "old.txt"]
    with pytest.raises(OutputError) as plain:
        write_files(tmp_path, FILES, force=False, slug=SLUG)
    assert "also removes" not in str(plain.value)


def test_remove_ignores_directories_and_links_and_names_it_cannot_remove(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    (tmp_path / "keep.txt").write_bytes(b"keep")
    if os.name == "posix":
        (tmp_path / "link").symlink_to(tmp_path / "keep.txt")
    write_files(tmp_path, FILES, force=True, slug=SLUG, remove=["folder", "link", "absent"])
    assert (tmp_path / "folder").is_dir()
    assert (tmp_path / "keep.txt").read_bytes() == b"keep"
    if os.name == "posix":
        assert (tmp_path / "link").is_symlink()


def test_a_failed_forced_replace_restores_the_removed_files_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (*FILES, "old.txt"):
        (tmp_path / name).write_bytes(b"old " + name.encode())
    real_replace = Path.replace
    calls = {"n": 0}

    def replace(self: Path, target: Path) -> Path:
        calls["n"] += 1
        # three moves to backups (two targets and the stale file), then the first new file
        # goes in, then the second fails
        if calls["n"] == 5:
            raise OSError(5, "Input/output error")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OutputError, match="the directory is unchanged"):
        write_files(tmp_path, FILES, force=True, slug=SLUG, remove=["old.txt"])
    monkeypatch.undo()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == {
        name: b"old " + name.encode() for name in (*FILES, "old.txt")
    }


def test_a_permission_error_while_checking_targets_is_an_output_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: Path, **_: object) -> bool:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "is_dir", refuse)
    with pytest.raises(OutputError, match=r"cannot check .* for existing files: Permission denied"):
        write_files(tmp_path / "out", FILES, force=False, slug=SLUG)
    monkeypatch.undo()
    assert not list((tmp_path / "out").iterdir())


def test_a_path_that_is_not_utf8_is_shown_as_an_escape_in_a_message(tmp_path: Path) -> None:
    blocker = tmp_path / "file-\udcff"
    try:
        blocker.write_bytes(b"x")
    except (OSError, UnicodeEncodeError):
        pytest.skip("this file system refuses a name that is not UTF-8")
    with pytest.raises(OutputError, match=r"cannot create .*file-\\xff") as caught:
        write_files(blocker / "sub", FILES, force=False, slug=SLUG)
    str(caught.value).encode("utf-8")  # a message must always be printable


# copy_new ---------------------------------------------------------------------------------


def test_copy_new_creates_a_private_copy_and_never_replaces(tmp_path: Path) -> None:
    source = tmp_path / "source.tmp"
    source.write_bytes(b"content")
    target = tmp_path / "target.txt"
    copy_new(source, target)
    assert target.read_bytes() == b"content"
    assert source.read_bytes() == b"content"
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        copy_new(source, target)
    assert target.read_bytes() == b"content"


# The guard against replacing a file that is read -------------------------------------------

needs_links = pytest.mark.skipif(
    sys.platform == "win32", reason="creating a link needs a privilege on Windows"
)


@pytest.mark.parametrize("kind", ["same path", "dotdot", "symlink", "hardlink"])
@pytest.mark.parametrize("force", [False, True])
def test_a_target_that_is_a_protected_file_is_refused_even_with_force(
    tmp_path: Path, kind: str, *, force: bool
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    target = out / "a.txt"
    evidence = tmp_path / "evidence.evtx"
    evidence.write_bytes(b"evidence bytes")
    given = evidence
    try:
        if kind == "symlink":
            target.symlink_to(evidence)
        elif kind == "hardlink":
            os.link(evidence, target)
        else:  # the evidence itself sits at the name an output file would take
            target.write_bytes(b"evidence bytes")
            given = target if kind == "same path" else out / ".." / "out" / "a.txt"
    except (OSError, NotImplementedError):
        pytest.skip(f"{kind}s are not available here")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(OutputError, match="same file as the input file"):
        write_files(out, FILES, force=force, slug=SLUG, protect=[("input file", given)])
    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before  # the evidence, the aliases, and every other file are untouched
    assert not list(tmp_path.rglob(f".{SLUG}-*"))


def test_files_that_are_not_protected_are_still_written_with_force(tmp_path: Path) -> None:
    other = tmp_path / "other.evtx"
    other.write_bytes(b"x")
    (tmp_path / "a.txt").write_bytes(b"old")
    write_files(tmp_path, FILES, force=True, slug=SLUG, protect=[("input file", other)])
    assert (tmp_path / "a.txt").read_bytes() == FILES["a.txt"]
    assert other.read_bytes() == b"x"


def test_a_protected_file_that_does_not_exist_protects_nothing(tmp_path: Path) -> None:
    protect = [("input file", tmp_path / "missing")]
    write_files(tmp_path, FILES, force=False, slug=SLUG, protect=protect)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt", "b.txt"]


def test_the_message_names_the_target_the_role_and_the_protected_path(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_bytes(b"mine")
    with pytest.raises(OutputError) as caught:
        refuse_aliases([source], [("CA file", source)])
    assert str(caught.value) == (
        f"{source} is the same file as the CA file {source}; a file that is read is never "
        "replaced, even with --force; choose another output location"
    )


def test_every_target_is_checked_against_every_protected_path(tmp_path: Path) -> None:
    one, two = tmp_path / "one.txt", tmp_path / "two.txt"
    one.write_bytes(b"1")
    two.write_bytes(b"2")
    refuse_aliases([tmp_path / "new.txt"], [("input", one), ("input", two)])
    refuse_aliases([], [("input", one)])
    refuse_aliases([one], [])
    with pytest.raises(OutputError, match="same file"):
        refuse_aliases([tmp_path / "new.txt", two], [("input", one), ("input", two)])


def test_the_guard_ignores_names_that_reach_nothing(tmp_path: Path) -> None:
    source = tmp_path / "evidence.json"
    source.write_text("x", encoding="utf-8")
    refuse_aliases([tmp_path / "missing-dir" / "a.txt"], [("input", source)])
    refuse_aliases([tmp_path / "a.txt"], [("input", tmp_path / "gone.json")])
    refuse_aliases([tmp_path / "evidence.json" / "below"], [("input", source)])  # ENOTDIR
    with pytest.raises(OutputError, match="is the same file as the input"):
        refuse_aliases([tmp_path / "evidence.json"], [("input", source)])


def test_an_output_directory_under_a_file_is_not_an_alias(tmp_path: Path) -> None:
    source = tmp_path / "e.csv"
    source.write_text("id\n", encoding="utf-8")
    refuse_aliases([source / "sub" / "a.txt"], [("input", source)])
    refuse_aliases([tmp_path / "a.txt"], [("input", tmp_path / "absent.csv")])


def test_a_comparison_that_cannot_be_made_refuses_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uncertain answer is a refusal, never a pass."""
    source = tmp_path / "e.csv"
    source.write_text("id\n", encoding="utf-8")

    def denied(self: Path, _other: object) -> bool:
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "samefile", denied)
    with pytest.raises(OutputError, match=r"cannot tell whether .* is the input .*Permission"):
        refuse_aliases([tmp_path / "a.txt"], [("input", source)])
    with pytest.raises(OutputError, match="cannot tell"):
        write_files(tmp_path, FILES, force=True, slug=SLUG, protect=[("input", source)])
    assert [p.name for p in tmp_path.iterdir()] == ["e.csv"]


def test_a_failure_while_resolving_paths_refuses_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_path: object) -> str:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(os.path, "realpath", broken)
    with pytest.raises(OutputError, match=r"cannot compare .*: Input/output error"):
        refuse_aliases([tmp_path / "a.txt"], [("input", tmp_path / "in.txt")])


# Folders that are read ----------------------------------------------------------------------


def make_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "bk"
    (folder / "sub").mkdir(parents=True)
    (folder / "sub" / "report.xml").write_bytes(b"part of the folder")
    return folder


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("where", ["the folder itself", "a new folder inside", "a deep new folder"])
def test_nothing_is_published_inside_a_protected_folder(
    tmp_path: Path, where: str, *, force: bool
) -> None:
    folder = make_folder(tmp_path)
    out = {
        "the folder itself": folder,
        "a new folder inside": folder / "reports",
        "a deep new folder": folder / "sub" / "x" / "y",
    }[where]
    before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    with pytest.raises(OutputError, match=r"would be written inside the input folder .*bk"):
        write_files(out, FILES, force=force, slug=SLUG, protect=[("input folder", folder)])
    assert {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()} == before
    assert not (folder / "reports").exists()
    assert not (folder / "sub" / "x").exists()


def test_a_folder_beside_a_protected_folder_is_fine(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    for out in (tmp_path / "reports", tmp_path / "bk-reports", folder.parent):
        write_files(out, FILES, force=True, slug=SLUG, protect=[("input folder", folder)])
        assert (out / "a.txt").is_file()


@needs_links
def test_an_output_folder_that_is_a_link_to_a_protected_folder_is_refused(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(folder, target_is_directory=True)
    with pytest.raises(OutputError, match="would be written inside the input folder"):
        write_files(alias, FILES, force=True, slug=SLUG, protect=[("input folder", folder)])
    assert sorted(p.name for p in folder.iterdir()) == ["sub"]


@needs_links
def test_a_link_from_the_output_folder_into_a_protected_folder_is_refused(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "inner").symlink_to(folder / "sub", target_is_directory=True)
    with pytest.raises(OutputError, match="would be written inside the input folder"):
        write_files(out / "inner", FILES, force=True, slug=SLUG, protect=[("input folder", folder)])


@needs_links
def test_a_hard_link_to_a_file_in_a_protected_folder_is_refused(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    try:
        os.link(folder / "sub" / "report.xml", out / "a.txt")
    except OSError:
        pytest.skip("hard links are not available here")
    with pytest.raises(OutputError, match="would be written inside the input folder"):
        write_files(out, FILES, force=True, slug=SLUG, protect=[("input folder", folder)])
    assert (folder / "sub" / "report.xml").read_bytes() == b"part of the folder"
    assert (out / "a.txt").read_bytes() == b"part of the folder"


@needs_links
def test_a_hard_link_to_a_file_outside_a_protected_folder_is_fine(tmp_path: Path) -> None:
    folder = make_folder(tmp_path)
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_bytes(b"x")
    out = tmp_path / "out"
    out.mkdir()
    try:
        os.link(elsewhere, out / "a.txt")
    except OSError:
        pytest.skip("hard links are not available here")
    write_files(out, FILES, force=True, slug=SLUG, protect=[("input folder", folder)])
    assert (out / "a.txt").read_bytes() == FILES["a.txt"]
    assert elsewhere.read_bytes() == b"x"


def test_a_protected_folder_that_does_not_exist_protects_nothing(tmp_path: Path) -> None:
    write_files(
        tmp_path / "out", FILES, force=False, slug=SLUG, protect=[("input folder", tmp_path / "no")]
    )
    assert (tmp_path / "out" / "a.txt").is_file()


def test_an_existing_file_with_one_name_is_not_a_second_name_for_a_protected_file(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.txt").write_bytes(b"old")
    write_files(out, FILES, force=True, slug=SLUG, protect=[("input folder", folder)])
    assert (out / "a.txt").read_bytes() == FILES["a.txt"]


def test_a_target_that_cannot_be_examined_refuses_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = make_folder(tmp_path)
    real_stat = Path.stat

    def stat(self: Path, **kwargs: Any) -> os.stat_result:
        if self.name == "a.txt":
            raise PermissionError(13, "Permission denied", str(self))
        return real_stat(self, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(OutputError, match=r"cannot compare .*: Permission denied"):
        refuse_aliases([tmp_path / "out" / "a.txt"], [("input folder", folder)])
