# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Printing never changes an exit code that is already decided."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

import pytest

from faithful_core import console

if TYPE_CHECKING:
    from collections.abc import Iterator

# A tiny program that prints, then exits with a code it decided first. It waits for a byte on
# standard input before printing, so a test can close the reading end of its output first.
PROGRAM = textwrap.dedent(
    """
    import sys
    from faithful_core import console

    console.prepare()
    sys.stdin.buffer.read(1)
    console.say("d\\u00e9mo \\u4e2d first")
    console.say("second", end="!\\n")
    console.say("to stderr", error=True)
    console.finish()
    sys.exit(7)
    """
)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close the null device that a closed pipe leaves behind, and start printing again."""
    assert monkeypatch is not None  # undone after this fixture, so prepare() sees the fakes
    yield
    console.prepare()


class Closed(io.TextIOBase):
    """A standard output whose reader has gone away."""

    def __init__(self, *, fail_on: str = "write", error: type[OSError | ValueError]) -> None:
        self.fail_on = fail_on
        self.error = error

    def _fail(self) -> Exception:
        if self.error is OSError:
            return BrokenPipeError(32, "Broken pipe")
        return ValueError("I/O operation on closed file")

    def write(self, text: str) -> int:
        if self.fail_on == "write":
            raise self._fail()
        return len(text)

    def flush(self) -> None:
        if self.fail_on == "flush":
            raise self._fail()

    def close(self) -> None:
        """Do nothing, so that collecting the object does not flush it again."""


def child(*, close_stdout: bool = False, **env: str) -> tuple[int, bytes, bytes]:
    """Run PROGRAM and return its exit code, standard output, and standard error."""
    clean = {k: v for k, v in os.environ.items() if k not in {"PYTHONIOENCODING", "PYTHONUTF8"}}
    with subprocess.Popen(  # noqa: S603 - this interpreter, a program the test wrote
        [sys.executable, "-c", PROGRAM],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**clean, **env},
    ) as process:
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        if close_stdout:
            process.stdout.close()  # the reader goes away before the child prints
        process.stdin.write(b"go")
        process.stdin.close()
        stderr = process.stderr.read()
        out = b"" if close_stdout else process.stdout.read()
        # Text streams on Windows write a line ending as CRLF; compare in one form.
        out, stderr = out.replace(b"\r\n", b"\n"), stderr.replace(b"\r\n", b"\n")
        return process.wait(timeout=120), out, stderr


# --- the ordinary cases ------------------------------------------------------------------


def test_say_writes_a_line_to_standard_output(capsys: pytest.CaptureFixture[str]) -> None:
    console.say("hello")
    console.say()
    console.say("no newline", end="")
    captured = capsys.readouterr()
    assert captured.out == "hello\n\nno newline"
    assert captured.err == ""


def test_say_writes_to_standard_error_with_error(capsys: pytest.CaptureFixture[str]) -> None:
    console.say("problem", error=True)
    console.say("more", error=True, end="")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "problem\nmore"


def test_finish_flushes_both_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    flushed: list[str] = []

    class Stream(io.StringIO):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name_ = name

        def flush(self) -> None:
            flushed.append(self.name_)

    monkeypatch.setattr(sys, "stdout", Stream("out"))
    monkeypatch.setattr(sys, "stderr", Stream("err"))
    console.finish()
    assert flushed == ["out", "err"]


# --- a character the stream cannot encode ------------------------------------------------


def test_ascii_only_output_keeps_the_exit_code_and_shows_escapes() -> None:
    code, out, err = child(PYTHONIOENCODING="ascii")
    assert code == 7
    assert out == b"d\\xe9mo \\u4e2d first\nsecond!\n"
    assert err == b"to stderr\n"


def test_an_ascii_stream_in_this_process_does_not_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="ascii", newline="\n", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    console.prepare()
    console.say("démo")
    assert raw.getvalue() == b"d\\xe9mo\n"


def test_a_stream_that_cannot_be_reconfigured_is_still_written_in_ascii(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Stubborn(io.TextIOWrapper):
        def reconfigure(self, *_args: object, **_kwargs: object) -> None:
            raise ValueError("no")

    raw = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", Stubborn(raw, encoding="ascii", newline="\n", write_through=True)
    )
    console.prepare()
    console.say("démo")
    assert raw.getvalue() == b"d\\xe9mo\n"


# --- a closed pipe -----------------------------------------------------------------------


def test_a_closed_pipe_in_a_real_process_keeps_the_exit_code_and_stays_quiet() -> None:
    code, _out, err = child(close_stdout=True)
    assert code == 7
    assert b"Traceback" not in err
    assert b"BrokenPipe" not in err
    assert err == b"to stderr\n"  # standard error still works


@pytest.mark.parametrize("error", [OSError, ValueError])
@pytest.mark.parametrize("fail_on", ["write", "flush"])
def test_a_closed_pipe_does_not_raise_and_stdout_goes_to_the_null_device(
    monkeypatch: pytest.MonkeyPatch, fail_on: str, error: type[OSError | ValueError]
) -> None:
    monkeypatch.setattr(sys, "stdout", Closed(fail_on=fail_on, error=error))
    console.say("one")
    console.say("two")
    console.finish()
    assert sys.stdout is not None
    if fail_on == "write":
        assert sys.stdout.name == os.devnull


def test_say_to_standard_error_survives_a_closed_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", Closed(error=ValueError))
    console.say("hello", error=True)  # must not raise


def test_a_closed_standard_output_object_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", Closed(error=ValueError))
    monkeypatch.setattr(sys, "stderr", Closed(error=ValueError))
    console.prepare()
    console.say("hello")
    console.say("again")  # printing has stopped, so this is skipped
    console.finish()  # nothing to flush to, and no error


def test_standard_error_is_not_silenced_by_a_closed_standard_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdout", Closed(error=OSError))
    console.say("lost")
    console.say("kept", error=True)
    assert capsys.readouterr().err == "kept\n"


def test_prepare_starts_printing_again_after_an_earlier_closed_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", Closed(error=OSError))
    console.say("x")
    assert sys.stdout.name == os.devnull
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sink)
    console.prepare()
    console.say("back")
    assert sink.getvalue() == "back\n"


def test_stdout_closed_can_be_called_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stdout", sink)
    console.stdout_closed()
    assert sys.stdout is not sink
    console.say("dropped")
    assert sink.getvalue() == ""
