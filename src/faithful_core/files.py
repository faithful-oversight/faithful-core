# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Publish a set of output files together, privately, and without clobbering.

Guarantees, stated exactly:

- File contents are written unchanged. Text is encoded as UTF-8 with no newline
  translation; bytes are written as they are.
- Files are written to private temporary files in the target directory first,
  then placed under their final names in order, so the last name in ``files``
  appears last. A caller that puts its manifest last can promise that a manifest
  means every other file is in place.
- On file systems with hard links, every file is complete before it appears
  under its final name.
- On file systems without hard links, such as FAT and exFAT, a file is created
  exclusively under its final name and written there, so it is visible while
  being written. If writing fails, the file that was created is removed.
- Without ``force``, an existing file is never replaced, even if it appears
  after the initial check. Placing a file fails if the name already exists.
- With ``force``, existing files are moved aside before the new ones go in. If
  any step fails, the new files that were placed are removed and the old ones are
  restored, so the directory holds either the complete old set or the complete
  new set.
- With ``force``, the plain files named in ``remove`` (the files of an earlier
  run that this run does not write) go in the same all-or-nothing swap.
- New files are readable only by the current user on Linux and macOS. A
  symbolic link at a target name is replaced, never followed.
- A target that is the same file as one the caller protects (an input, for
  instance), or that would sit inside a protected folder, is refused, with or
  without ``force``, before anything is written. "The same file" is decided by
  the file system after links, ``..`` and case are resolved, so a symbolic link,
  a hard link, or another spelling of the path does not get around it. When the
  file system cannot answer, the answer is a refusal.

One process at a time may write to an output directory. Two runs writing to the
same directory at once can remove or restore each other's files.

A crash or power loss in the middle of publishing can still leave a mix of old
and new files, a partly written file on file systems without hard links, and
``.<slug>-old-*`` backups. A manifest that lists the size and SHA-256 of every
file makes an incomplete or mixed set detectable.
"""

from __future__ import annotations

import errno
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from faithful_core.errors import OutputError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__ = ["copy_new", "refuse_aliases", "write_files"]

_NOT_THERE = {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}
"""``No such file`` answers: a name that reaches nothing cannot be a protected file."""
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _shown(path: Path | str) -> str:
    r"""Return a path as valid text for a message; bytes that are not UTF-8 show as ``\xff``."""
    return os.fsencode(str(path)).decode("utf-8", "backslashreplace")


def refuse_aliases(targets: Iterable[Path], protect: Iterable[tuple[str, Path]]) -> None:
    """Refuse a target that is a protected file, or that would sit inside a protected folder.

    Args:
        targets: The paths about to be written. They need not exist yet.
        protect: ``(role, path)`` pairs for files and folders that must not be replaced or
            written into, such as ``("input file", path)``. The role is used in the message.

    Raises:
        OutputError: A target and a protected file are one file, a target is, or would be,
            inside a protected folder, or the file system cannot tell which. A protected
            path that does not exist protects nothing.
    """
    held = [(role, Path(path)) for role, path in protect]
    if not held:
        return
    try:
        for target in map(Path, targets):
            planned = Path(os.path.realpath(target.parent)) / target.name
            resolved = Path(os.path.realpath(target))
            for role, path in held:
                _refuse_if_same(role, path, target, planned, resolved)
    except OSError as exc:
        msg = (
            "cannot compare the output files with the files and folders that are read: "
            f"{exc.strerror}; choose another output location"
        )
        raise OutputError(msg) from exc


def _refuse_if_same(role: str, path: Path, target: Path, planned: Path, resolved: Path) -> None:
    """Raise when ``target`` is ``path`` (or inside it, for a folder)."""
    real_path = Path(os.path.realpath(path))
    if path.is_dir():
        inside = real_path in (planned, resolved, *planned.parents, *resolved.parents)
        if inside or _hard_link_inside(path, target):
            msg = (
                f"the output file {_shown(target)} would be written inside the {role} "
                f"{_shown(path)}, which would change it; choose another output location"
            )
            raise OutputError(msg)
        return
    if real_path in (planned, resolved) or _samefile(path, target, role):
        msg = (
            f"{_shown(target)} is the same file as the {role} {_shown(path)}; a file that is "
            "read is never replaced, even with --force; choose another output location"
        )
        raise OutputError(msg)


def _samefile(path: Path, target: Path, role: str) -> bool:
    """Whether the two names reach one file; an answer that cannot be had is a refusal."""
    try:
        return path.samefile(target)
    except OSError as exc:
        if exc.errno in _NOT_THERE:
            return False
        msg = (
            f"cannot tell whether {_shown(target)} is the {role} {_shown(path)}: "
            f"{exc.strerror}; choose another output location"
        )
        raise OutputError(msg) from exc


def _hard_link_inside(folder: Path, target: Path) -> bool:
    """Whether an existing target is a second name for a file inside ``folder``."""
    try:
        found = target.stat()
    except OSError as exc:
        if exc.errno in _NOT_THERE:
            return False
        raise
    if found.st_nlink < 2:  # noqa: PLR2004 - a file with one name has no other name to find
        return False
    return any(
        (member.stat().st_dev, member.stat().st_ino) == (found.st_dev, found.st_ino)
        for member in folder.rglob("*")
        if member.is_file()
    )


def write_files(  # noqa: PLR0913 - one call states the whole publish: where, what, and the guards
    directory: Path,
    files: Mapping[str, str | bytes],
    *,
    force: bool,
    slug: str,
    protect: Iterable[tuple[str, Path]] = (),
    remove: Iterable[str] = (),
) -> list[Path]:
    """Publish every file, or leave the directory as it was.

    Args:
        directory: The output directory. It is created when missing.
        files: The content of each file, by name, in the order the files must appear. Text
            is encoded as UTF-8 and written with no newline translation.
        force: Replace files that exist.
        slug: A short name for the calling tool. Temporary files are named
            ``.<slug>-*.tmp`` and ``.<slug>-old-*.bak``.
        protect: ``(role, path)`` pairs for files and folders that must never be replaced
            or written into; see :func:`refuse_aliases`.
        remove: Names of files from an earlier run that this run does not write. With
            ``force`` the plain files among them are removed in the same swap.

    Returns:
        The paths of the files, in the order of ``files``.

    Raises:
        OutputError: A target exists and ``force`` is false, a target is a directory, a
            target is a protected file, or writing fails. The directory is left as it was.
        ValueError: ``slug`` is not usable in a file name. This is a programming error.
    """
    if not _SLUG.fullmatch(slug):
        msg = f"slug {slug!r} cannot be used in a file name"
        raise ValueError(msg)
    refuse_aliases((directory / name for name in files), protect)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        msg = f"cannot create {_shown(directory)}: {exc.strerror}"
        raise OutputError(msg) from exc
    targets = [directory / name for name in files]
    removing = [name for name in remove if name not in files]
    try:
        _check_targets(targets, force=force, removing=bool(removing))
    except OSError as exc:
        msg = f"cannot check {_shown(directory)} for existing files: {exc.strerror}"
        raise OutputError(msg) from exc

    staged: list[Path] = []
    try:
        staged.extend(_stage(directory, data, slug) for data in files.values())
        pairs = list(zip(staged, targets, strict=True))
        if force:
            stale = [directory / name for name in removing]
            _replace_all(directory, pairs, [p for p in stale if _plain_file(p)], slug)
        else:
            _link_all(pairs)
    except OSError as exc:
        msg = (
            f"cannot write files in {_shown(directory)}: {exc.strerror}; the directory is unchanged"
        )
        raise OutputError(msg) from exc
    finally:
        for temp in staged:
            temp.unlink(missing_ok=True)
    return targets


def _check_targets(targets: list[Path], *, force: bool, removing: bool) -> None:
    folders = [_shown(t) for t in targets if t.is_dir() and not t.is_symlink()]
    if folders:
        msg = f"{', '.join(folders)} is a directory; choose another output directory"
        raise OutputError(msg)
    existing = [_shown(t) for t in targets if t.exists() or t.is_symlink()]
    if existing and not force:
        one = len(existing) == 1
        msg = (
            f"{', '.join(existing)} already {'exists' if one else 'exist'}; "
            f"use --force to replace {'it' if one else 'them'}"
        )
        if removing:
            msg += (
                ", or choose another folder (--force also removes files an earlier run wrote "
                "and this run does not)"
            )
        raise OutputError(msg)


def _stage(directory: Path, data: str | bytes, slug: str) -> Path:
    """Write the content to a new private temporary file and return its path."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, temp = tempfile.mkstemp(dir=directory, prefix=f".{slug}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return Path(temp)


def _link_all(pairs: list[tuple[Path, Path]]) -> None:
    """Place each file only if its name is free; undo every placement on failure."""
    placed: list[Path] = []
    try:
        for temp, target in pairs:
            _place_new(temp, target)
            placed.append(target)
    except FileExistsError as exc:
        _remove(placed)
        msg = f"{_shown(str(exc.filename))} appeared while writing; use --force to replace"
        raise OutputError(msg) from exc
    except BaseException:
        _remove(placed)
        raise


def _place_new(temp: Path, target: Path) -> None:
    """Create ``target`` with the content of ``temp``, failing if it exists."""
    try:
        os.link(temp, target)
    except FileExistsError:
        raise
    except OSError:
        copy_new(temp, target)


def copy_new(temp: Path, target: Path) -> None:
    """Create ``target`` from ``temp`` for file systems with no hard links.

    The name is created with ``O_EXCL``, so it belongs to this call until the content is
    complete. Any failure after that removes it again. An existing name is never touched:
    :class:`FileExistsError` is raised and the file stays as it was.
    """
    data = temp.read_bytes()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        handle = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        target.unlink(missing_ok=True)
        raise
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _replace_all(
    directory: Path, pairs: list[tuple[Path, Path]], stale: list[Path], slug: str
) -> None:
    """Swap in every new file and take away ``stale``, restoring the old set on failure."""
    backups: list[tuple[Path, Path]] = []
    placed: list[Path] = []
    try:
        for target in [*(t for _, t in pairs), *stale]:
            if target.exists() or target.is_symlink():
                backup = _backup_name(directory, slug)
                try:
                    target.replace(backup)
                except BaseException:
                    backup.unlink(missing_ok=True)
                    raise
                backups.append((backup, target))
        for temp, target in pairs:
            temp.replace(target)
            placed.append(target)
    except BaseException:
        _remove(placed)
        for backup, target in backups:
            backup.replace(target)
        raise
    _remove([backup for backup, _ in backups])


def _backup_name(directory: Path, slug: str) -> Path:
    fd, name = tempfile.mkstemp(dir=directory, prefix=f".{slug}-old-", suffix=".bak")
    os.close(fd)
    return Path(name)


def _remove(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
