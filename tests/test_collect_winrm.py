# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""The WinRM collection plumbing, with a stand-in for pypsrp and a small test sink.

Set ``FAITHFUL_CORE_REQUIRE_WINRM=1`` to fail instead of skipping when the ``winrm`` extra
(pypsrp) is missing.
"""

from __future__ import annotations

import errno
import hashlib
import importlib
import os
import sys
import types
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from faithful_core.collect import secrets, winrm
from faithful_core.collect.winrm import Target, collect, publish_file, settings
from faithful_core.errors import CollectionError

if os.environ.get("FAITHFUL_CORE_REQUIRE_WINRM") == "1":  # pragma: no cover - set in CI
    # Fail at collection, not skip, when the extra is missing. Imported by name so type
    # checking does not need the extra installed.
    importlib.import_module("pypsrp")

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

SECRET = 'p@ss w/rd%"\\ü'  # noqa: S105 - synthetic
SERVER = "dc01.corp.example"
TARGET = Target(SERVER, "kerberos", "CORP\\auditor", SECRET)
HINT = 'pipx install --force "faithful-example[winrm]"'
RUNNING, COMPLETED, FAILED = 1, 4, 5

BODY = ["header", "one", "two"]
DIGEST = hashlib.sha256(b"".join(f"{line}\n".encode() for line in BODY)).hexdigest()
END = f"END 3 {DIGEST}"
LINES = [*BODY, END]


@pytest.fixture(autouse=True)
def forget_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test with no remembered secret."""
    monkeypatch.setattr(secrets, "_resolved", set())


# --- a small sink: the contract a product implements -----------------------------------


class LineSink:
    """Keep ASCII lines in a private file; the last line says how many came and their hash."""

    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.temp = destination.parent / f".{destination.name}.part"
        descriptor = os.open(self.temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.handle = os.fdopen(descriptor, "wb")
        self.digest = hashlib.sha256()
        self.lines = 0
        self.end: list[str] | None = None
        self.noun = "collector"

    @property
    def ended(self) -> bool:
        return self.end is not None

    def take(self, item: object) -> None:
        if self.ended:
            msg = f"the {self.noun} sent output after its end line"
            raise CollectionError(msg)
        if not isinstance(item, str) or not item.isascii() or "\n" in item:
            msg = f"the {self.noun} sent something that is not one line of text"
            raise CollectionError(msg)
        raw = item.encode("ascii") + b"\n"
        self.handle.write(raw)
        if item.startswith("END "):
            self.end = item.split()
        else:
            self.digest.update(raw)
            self.lines += 1

    def finish(self) -> tuple[int, str]:
        self.handle.close()
        if self.end is None:
            msg = "the collection ended without its end line, so it did not finish"
            raise CollectionError(msg)
        count, digest = int(self.end[1]), self.end[2]
        if count != self.lines or digest != self.digest.hexdigest():
            msg = "the end line does not match what arrived"
            raise CollectionError(msg)
        return self.lines, str(digest)

    def publish(self, *, force: bool) -> None:
        publish_file(self.temp, self.destination, force=force)

    def discard(self) -> None:
        self.handle.close()
        self.temp.unlink(missing_ok=True)


# --- a stand-in for pypsrp -------------------------------------------------------------


class Remote:
    """The parts of pypsrp that the module uses, replaying chosen output in chosen batches."""

    def __init__(self, batches: Sequence[Sequence[object]], *, end: int = COMPLETED) -> None:
        self.batches: list[Sequence[object]] = list(batches)
        self.end = end
        self.settings: dict[str, Any] = {}
        self.script = ""
        self.parameters: dict[str, Any] = {}
        self.error: Exception | BaseException | None = None
        self.errors: list[str] = []
        self.stopped = False
        self.hints: list[str] = []

    def client(self, hint: str) -> tuple[Any, Any, Any, int]:  # noqa: C901 - one small class per part
        self.hints.append(hint)
        remote_side = self

        class WSMan:
            def __init__(self, **values: Any) -> None:
                remote_side.settings = values
                if remote_side.error is not None:
                    raise remote_side.error

            def __enter__(self) -> WSMan:
                return self

            def __exit__(self, *_: object) -> None:
                return None

        class Pool:
            def __init__(self, _: object) -> None:
                pass

            def __enter__(self) -> Pool:
                return self

            def __exit__(self, *_: object) -> None:
                return None

        class Streams:
            error = remote_side.errors

        class Shell:
            def __init__(self, _: object) -> None:
                self.state = RUNNING
                self.output: list[object] = []
                self.had_errors = False
                self.streams = Streams()

            def add_script(self, text: str) -> None:
                remote_side.script = text

            def add_parameters(self, values: dict[str, Any]) -> None:
                remote_side.parameters = values

            def begin_invoke(self) -> None:
                pass

            def poll_invoke(self, timeout: int) -> None:
                assert timeout == winrm.POLL_SECONDS
                if remote_side.batches:
                    self.output.extend(remote_side.batches.pop(0))
                if not remote_side.batches:
                    self.state = remote_side.end
                    self.had_errors = remote_side.end == FAILED

            def stop(self) -> None:
                remote_side.stopped = True
                msg = "stop is best effort"
                raise RuntimeError(msg)

        return WSMan, Pool, Shell, RUNNING


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Remote:
    side = Remote([LINES[:2], [], LINES[2:]])
    monkeypatch.setattr(winrm, "client", side.client)
    return side


def run(destination: Path, **options: Any) -> Any:
    sink = options.pop("sink", None) or LineSink(destination)
    return collect(
        options.pop("target", TARGET),
        "script text",
        {"ToPipeline": True},
        destination,
        sink=sink,
        noun=options.pop("noun", "collector"),
        hint=HINT,
        force=options.pop("force", False),
        **options,
    )


def leftovers(folder: Path) -> list[str]:
    return sorted(path.name for path in folder.iterdir() if path.name.endswith(".part"))


# --- transport settings ----------------------------------------------------------------


def test_the_secret_is_not_in_the_targets_repr() -> None:
    assert SECRET not in repr(TARGET)


def test_https_always_verifies_the_certificate(tmp_path: Path) -> None:
    values = settings(TARGET)
    assert (values["ssl"], values["port"], values["cert_validation"], values["encryption"]) == (
        True, 5986, True, "auto",
    )  # fmt: skip
    ca = tmp_path / "corp-ca.pem"
    with_ca = settings(replace(TARGET, ca_file=ca, port=443))
    assert (with_ca["cert_validation"], with_ca["port"]) == (str(ca), 443)


@pytest.mark.parametrize("auth", winrm.AUTHS)
def test_http_is_used_only_with_message_encryption(auth: str) -> None:
    values = settings(replace(TARGET, auth=auth, transport="http"))
    assert (values["ssl"], values["port"], values["encryption"]) == (False, 5985, "always")


def test_no_setting_turns_verification_off() -> None:
    for transport in winrm.TRANSPORTS:
        for auth in winrm.AUTHS:
            values = settings(replace(TARGET, transport=transport, auth=auth))
            assert values["cert_validation"] is True
            assert "verify" not in values
            assert values["password"] == SECRET


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"auth": "basic"}, "--auth must be one of"),
        ({"auth": "credssp"}, "--auth must be one of"),
        ({"transport": "ftp"}, "--auth must be one of"),
        ({"transport": "http", "ca_file": "x.pem"}, "--ca-file applies to https only"),
    ],
)
def test_insecure_combinations_are_refused(changes: dict[str, Any], problem: str) -> None:
    with pytest.raises(CollectionError, match=problem):
        settings(replace(TARGET, **changes))


def test_the_constants_are_the_documented_ones() -> None:
    assert winrm.AUTHS == ("kerberos", "negotiate", "ntlm")
    assert winrm.TRANSPORTS == ("https", "http")
    assert winrm.POLL_SECONDS == 5


@pytest.mark.parametrize(("transport", "wrapped"), [("https", False), ("http", True)])
def test_the_settings_reach_the_real_transport(transport: str, *, wrapped: bool) -> None:
    """The real pypsrp transport keeps verification on and wraps plain HTTP."""
    wsman_module = pytest.importorskip("pypsrp.wsman")
    wsman = wsman_module.WSMan(**settings(replace(TARGET, transport=transport, auth="ntlm")))
    transport_object = wsman.transport
    assert transport_object.cert_validation is True
    assert transport_object.ssl is (transport == "https")
    assert transport_object.wrap_required is wrapped
    assert transport_object.endpoint.startswith(f"{transport}://{SERVER}:")


# --- the client ------------------------------------------------------------------------


def test_the_real_client_classes_load() -> None:
    pytest.importorskip("pypsrp")
    wsman, pool, shell, running = winrm.client(HINT)
    assert (wsman.__name__, pool.__name__, shell.__name__, running) == (
        "WSMan", "RunspacePool", "PowerShell", RUNNING,
    )  # fmt: skip


def test_the_client_picks_the_classes_out_of_pypsrp(monkeypatch: pytest.MonkeyPatch) -> None:
    def module(name: str, **attributes: Any) -> None:
        monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(**attributes))

    module("pypsrp.wsman", WSMan="W")
    module("pypsrp.powershell", RunspacePool="R", PowerShell="P")
    module("pypsrp.complex_objects", PSInvocationState=types.SimpleNamespace(RUNNING=1))
    assert winrm.client(HINT) == ("W", "R", "P", 1)


@pytest.mark.parametrize("missing", ["pypsrp.wsman", "pypsrp.powershell", "pypsrp.complex_objects"])
def test_pypsrp_missing_says_how_to_install(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setitem(sys.modules, missing, None)
    with pytest.raises(CollectionError) as caught:
        winrm.client(HINT)
    assert str(caught.value) == f"remote collection needs pypsrp; install it with: {HINT}"


def test_importing_the_module_does_not_import_pypsrp() -> None:
    code = "import sys; import faithful_core.collect.winrm; assert 'pypsrp' not in sys.modules"
    import subprocess  # noqa: PLC0415 - only this test starts a process

    done = subprocess.run(  # noqa: S603 - this interpreter, a one-line program
        [sys.executable, "-c", code], capture_output=True, check=False, timeout=120
    )
    assert done.returncode == 0, done.stderr


# --- collect: the orchestration --------------------------------------------------------


def test_a_collection_streams_into_a_checked_file(tmp_path: Path, fake: Remote) -> None:
    out = tmp_path / "dc01-events.jsonl"
    lines, digest = run(out)
    assert (lines, digest) == (3, DIGEST)
    assert out.read_text(encoding="ascii") == "".join(f"{line}\n" for line in LINES)
    assert fake.settings["password"] == SECRET
    assert fake.settings["server"] == SERVER
    assert (fake.script, fake.parameters) == ("script text", {"ToPipeline": True})
    assert fake.hints == [HINT]
    assert leftovers(tmp_path) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == [out.name]


@pytest.mark.usefixtures("fake")
def test_collect_returns_whatever_the_sink_reports(tmp_path: Path) -> None:
    class Reports(LineSink):
        def finish(self) -> dict[str, int]:  # type: ignore[override]
            super().finish()
            return {"lines": self.lines}

    out = tmp_path / "e.txt"
    assert run(out, sink=Reports(out)) == {"lines": 3}


def test_the_secret_is_remembered_before_anything_can_leak_it(tmp_path: Path, fake: Remote) -> None:
    run(tmp_path / "e.txt")
    assert secrets.redact(f"x {SECRET} y") == "x [redacted] y"
    assert fake.settings["password"] == SECRET


def test_a_target_without_a_secret_remembers_nothing(tmp_path: Path, fake: Remote) -> None:
    run(tmp_path / "e.txt", target=Target(SERVER, "kerberos"))
    assert secrets.redact("nothing") == "nothing"
    assert fake.settings["username"] is None


@pytest.mark.parametrize(
    ("batches", "problem"),
    [
        ([LINES[:-1]], "ended without its end line"),
        ([[LINES[0], LINES[2], LINES[3]]], "does not match what arrived"),
        ([[*LINES, "extra"]], "output after its end line"),
        ([[LINES[0], 42]], "not one line of text"),
        ([[LINES[0], "a\nb"]], "not one line of text"),
        ([[LINES[0], "ü"]], "not one line of text"),
    ],
)
def test_a_damaged_collection_leaves_no_file(
    tmp_path: Path, fake: Remote, batches: list[Sequence[object]], problem: str
) -> None:
    fake.batches = batches
    out = tmp_path / "e.txt"
    with pytest.raises(CollectionError, match=problem):
        run(out)
    assert not out.exists()
    assert leftovers(tmp_path) == []


def test_a_damaged_collection_keeps_an_existing_file_even_with_force(
    tmp_path: Path, fake: Remote
) -> None:
    fake.batches = [LINES[:-1]]
    out = tmp_path / "e.txt"
    out.write_bytes(b"existing evidence\n")
    with pytest.raises(CollectionError, match="ended without its end line"):
        run(out, force=True)
    assert out.read_bytes() == b"existing evidence\n"
    assert leftovers(tmp_path) == []


def test_a_script_that_fails_reports_its_own_error_with_the_noun(
    tmp_path: Path, fake: Remote
) -> None:
    fake.batches = [LINES[:2]]
    fake.end = FAILED
    fake.errors.append(f"Access is denied for {SECRET}")
    with pytest.raises(CollectionError) as exc:
        run(tmp_path / "e.txt", noun="exporter")
    assert str(exc.value) == (
        "the exporter failed on dc01.corp.example: Access is denied for [redacted]"
    )
    fake.errors.clear()
    fake.batches = [LINES[:2]]
    with pytest.raises(
        CollectionError, match=r"the exporter failed .*: the script stopped with an"
    ):
        run(tmp_path / "e.txt", noun="exporter")
    assert leftovers(tmp_path) == []


def test_a_script_that_reports_errors_after_its_end_line_is_not_a_failure(
    tmp_path: Path, fake: Remote
) -> None:
    fake.end = FAILED  # had_errors is set, but the end line arrived: the collection finished
    assert run(tmp_path / "e.txt") == (3, DIGEST)


def test_a_stalled_collection_is_stopped_and_names_the_noun(tmp_path: Path, fake: Remote) -> None:
    fake.batches = [LINES[:1], [], [], [], LINES[1:]]
    ticks = iter(range(0, 10_000, 400))
    with pytest.raises(CollectionError, match="the exporter sent nothing for 600 seconds"):
        run(tmp_path / "e.txt", noun="exporter", clock=lambda: next(ticks))
    assert fake.stopped
    assert leftovers(tmp_path) == []


@pytest.mark.parametrize(
    "error", [OSError(f"connection refused, password={SECRET}"), ValueError("")]
)
def test_library_errors_never_show_the_secret(
    tmp_path: Path, fake: Remote, error: Exception
) -> None:
    fake.error = error
    with pytest.raises(CollectionError) as exc:
        run(tmp_path / "e.txt")
    assert SECRET not in str(exc.value)
    assert str(exc.value).startswith("remote collection from dc01.corp.example failed: ")
    assert exc.value.__cause__ is None  # the original, which holds the secret, is not chained
    assert leftovers(tmp_path) == []


def test_an_error_with_no_text_still_names_its_type(tmp_path: Path, fake: Remote) -> None:
    fake.error = ValueError("")
    with pytest.raises(CollectionError, match=r"failed: ValueError$"):
        run(tmp_path / "e.txt")


@pytest.mark.usefixtures("fake")
def test_a_collection_error_from_the_sink_is_redacted_too(tmp_path: Path) -> None:
    class Leaky(LineSink):
        def take(self, item: object) -> None:
            msg = f"the stream held {SECRET}"
            raise CollectionError(msg)

    out = tmp_path / "e.txt"
    with pytest.raises(CollectionError) as exc:
        run(out, sink=Leaky(out))
    assert str(exc.value) == "the stream held [redacted]"
    assert leftovers(tmp_path) == []


def test_an_interrupt_discards_the_private_file_and_is_not_swallowed(
    tmp_path: Path, fake: Remote
) -> None:
    fake.error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path / "e.txt")
    assert leftovers(tmp_path) == []


def test_the_sink_is_discarded_when_the_target_is_refused_before_connecting(
    tmp_path: Path, fake: Remote
) -> None:
    with pytest.raises(CollectionError, match="--auth must be one of"):
        run(tmp_path / "e.txt", target=replace(TARGET, auth="basic"))
    assert leftovers(tmp_path) == []
    assert fake.settings == {}


def test_pypsrp_missing_discards_the_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pypsrp.wsman", None)
    with pytest.raises(CollectionError, match="needs pypsrp; install it with: pipx"):
        run(tmp_path / "e.txt")
    assert leftovers(tmp_path) == []


def test_an_existing_file_is_kept_unless_forced(tmp_path: Path, fake: Remote) -> None:
    out = tmp_path / "e.txt"
    out.write_text("keep", encoding="utf-8")
    with pytest.raises(CollectionError, match="already exists; pass --force"):
        run(out)
    assert fake.settings == {}  # refused before connecting
    assert out.read_text(encoding="utf-8") == "keep"
    assert leftovers(tmp_path) == []
    run(out, force=True)
    assert out.read_text(encoding="ascii") == "".join(f"{line}\n" for line in LINES)


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
@pytest.mark.usefixtures("fake")
def test_a_link_at_the_destination_is_never_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("precious", encoding="utf-8")
    out = tmp_path / "e.txt"
    out.symlink_to(outside)
    with pytest.raises(CollectionError, match="already exists"):
        run(out)
    run(out, force=True)
    assert outside.read_text(encoding="utf-8") == "precious"
    assert not out.is_symlink()
    assert out.read_text(encoding="ascii").startswith("header\n")


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need privileges on Windows")
def test_a_dangling_link_at_the_destination_counts_as_existing(
    tmp_path: Path, fake: Remote
) -> None:
    out = tmp_path / "e.txt"
    out.symlink_to(tmp_path / "nowhere")
    with pytest.raises(CollectionError, match="already exists"):
        run(out)
    assert fake.settings == {}
    assert not (tmp_path / "nowhere").exists()


@pytest.mark.usefixtures("fake")
def test_a_file_that_appears_during_collection_is_not_clobbered(tmp_path: Path) -> None:
    out = tmp_path / "e.txt"

    class Racing(LineSink):
        def finish(self) -> tuple[int, str]:
            out.write_text("arrived", encoding="utf-8")
            return super().finish()

    with pytest.raises(CollectionError, match="already exists"):
        run(out, sink=Racing(out))
    assert out.read_text(encoding="utf-8") == "arrived"
    assert leftovers(tmp_path) == []


# --- the files the collection reads ----------------------------------------------------


def test_collect_refuses_a_destination_that_is_the_ca_file(tmp_path: Path, fake: Remote) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"ca bytes")
    with pytest.raises(CollectionError, match="same file as the CA file"):
        run(ca, target=replace(TARGET, ca_file=ca), force=True, sink=NullSink())
    assert ca.read_bytes() == b"ca bytes"
    assert fake.script == ""  # refused before connecting


class NullSink:
    """A sink for a test that must never reach the stream; it records being discarded."""

    ended = False

    def __init__(self) -> None:
        self.discarded = False

    def take(self, item: object) -> None:
        pytest.fail("nothing may be taken")

    def finish(self) -> None:
        pytest.fail("nothing may be finished")

    def publish(self, *, force: bool) -> None:
        pytest.fail("nothing may be published")

    def discard(self) -> None:
        self.discarded = True


def test_a_refused_destination_discards_the_sink(tmp_path: Path, fake: Remote) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"ca bytes")
    sink = NullSink()
    with pytest.raises(CollectionError, match="same file as the CA file"):
        run(ca, target=replace(TARGET, ca_file=ca), force=True, sink=sink)
    assert sink.discarded
    assert fake.settings == {}


@pytest.mark.usefixtures("fake")
def test_collect_checks_the_ca_file_again_just_before_publishing(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"ca bytes")
    out = tmp_path / "events.txt"

    class Aliasing(LineSink):
        def finish(self) -> tuple[int, str]:
            result = super().finish()
            os.link(ca, out)  # the destination becomes another name for the CA file
            return result

    with pytest.raises(CollectionError, match="same file as the CA file"):
        run(out, target=replace(TARGET, ca_file=ca), force=True, sink=Aliasing(out))
    assert ca.read_bytes() == b"ca bytes"
    assert out.read_bytes() == b"ca bytes"
    assert leftovers(tmp_path) == []


@pytest.mark.usefixtures("fake")
def test_a_destination_beside_the_ca_file_is_fine(tmp_path: Path) -> None:
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"ca bytes")
    out = tmp_path / "events.txt"
    assert run(out, target=replace(TARGET, ca_file=ca)) == (3, DIGEST)
    assert ca.read_bytes() == b"ca bytes"


# --- drain -----------------------------------------------------------------------------


class Shell:
    """A shell whose output arrives in chosen batches, one per poll."""

    def __init__(self, batches: list[list[object]]) -> None:
        self.batches = batches
        self.state = RUNNING
        self.output: list[object] = []
        self.polls = 0

    def poll_invoke(self, timeout: int) -> None:
        self.polls += 1
        if self.batches:
            self.output.extend(self.batches.pop(0))
        if not self.batches:
            self.state = COMPLETED

    def stop(self) -> None:
        self.state = FAILED


class Items:
    """A sink that only records what it is handed."""

    def __init__(self) -> None:
        self.taken: list[object] = []
        self.ended = False

    def take(self, item: object) -> None:
        self.taken.append(item)

    def finish(self) -> None:
        pass

    def publish(self, *, force: bool) -> None:
        pass

    def discard(self) -> None:
        pass


def test_drain_hands_over_every_item_and_clears_the_output() -> None:
    shell, items = Shell([["a", "b"], [], ["c"]]), Items()
    winrm.drain(shell, items, RUNNING, 600, lambda: 0.0, noun="collector")
    assert items.taken == ["a", "b", "c"]
    assert shell.output == []
    assert shell.polls == 3


def test_drain_takes_the_last_output_of_a_script_that_has_already_ended() -> None:
    shell, items = Shell([["a"]]), Items()
    shell.state = COMPLETED
    shell.output = ["late"]
    winrm.drain(shell, items, RUNNING, 600, lambda: 0.0, noun="collector")
    assert items.taken == ["late"]
    assert shell.polls == 0


def test_output_resets_the_idle_timer() -> None:
    shell, items = Shell([["a"], [], [], ["b"], [], []]), Items()
    ticks = iter([0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200])
    winrm.drain(shell, items, RUNNING, 350, lambda: float(next(ticks)), noun="collector")
    assert items.taken == ["a", "b"]


def test_drain_stops_a_script_that_goes_quiet() -> None:
    shell, items = Shell([["a"], [], [], [], ["never"]]), Items()
    ticks = iter(range(0, 10_000, 100))
    with pytest.raises(CollectionError, match="the exporter sent nothing for 150 seconds"):
        winrm.drain(shell, items, RUNNING, 150, lambda: float(next(ticks)), noun="exporter")
    assert shell.state == FAILED  # stop() was called
    assert items.taken == ["a"]


# --- publish_file ----------------------------------------------------------------------


def staged(tmp_path: Path, data: bytes = b"content") -> Path:
    temp = tmp_path / ".stage.part"
    temp.write_bytes(data)
    return temp


def no_hard_links(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Make ``os.link`` fail as on FAT; the count says how often it was tried."""
    calls = {"link": 0}

    def refuse(*_: object, **__: object) -> None:
        calls["link"] += 1
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(os, "link", refuse)
    return calls


def test_publish_file_links_the_file_into_place_and_consumes_the_temporary(
    tmp_path: Path,
) -> None:
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    publish_file(temp, out, force=False)
    assert out.read_bytes() == b"content"
    assert not temp.exists()


def test_publish_file_with_force_replaces(tmp_path: Path) -> None:
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    out.write_bytes(b"old")
    publish_file(temp, out, force=True)
    assert out.read_bytes() == b"content"
    assert not temp.exists()


def test_publish_file_without_force_never_replaces(tmp_path: Path) -> None:
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    out.write_bytes(b"old")
    with pytest.raises(CollectionError, match=r"out\.txt already exists; pass --force to replace"):
        publish_file(temp, out, force=False)
    assert out.read_bytes() == b"old"
    assert temp.exists()


def test_publish_file_with_force_reports_a_failure(tmp_path: Path) -> None:
    with pytest.raises(CollectionError, match=r"cannot write .*out\.txt: "):
        publish_file(tmp_path / "missing.part", tmp_path / "out.txt", force=True)


def test_publish_file_reports_a_failure_other_than_a_clash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    no_hard_links(monkeypatch)

    def full(_fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "fsync", full)
    with pytest.raises(CollectionError, match=r"cannot write .*out\.txt: No space left"):
        publish_file(temp, out, force=False)
    assert not out.exists()  # a failed copy removes what it created


def test_publish_file_works_on_a_file_system_without_hard_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = no_hard_links(monkeypatch)
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    publish_file(temp, out, force=False)
    assert calls["link"] == 1
    assert out.read_bytes() == b"content"
    assert not temp.exists()
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o600


def test_publish_file_without_hard_links_never_clobbers_a_name_that_appears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_hard_links(monkeypatch)
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    real_open = os.open

    def racing_open(path: str, flags: int, mode: int = 0o600) -> int:
        if str(path).endswith("out.txt"):
            out.write_bytes(b"arrived")
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", racing_open)
    with pytest.raises(CollectionError, match="already exists"):
        publish_file(temp, out, force=False)
    assert out.read_bytes() == b"arrived"


def test_the_helpers_are_importable_without_pypsrp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "pypsrp", None)
    temp, out = staged(tmp_path), tmp_path / "out.txt"
    publish_file(temp, out, force=False)
    assert [p.name for p in tmp_path.iterdir() if p.is_file()] == ["out.txt"]


def test_every_noun_in_a_message_comes_from_the_caller(tmp_path: Path, fake: Remote) -> None:
    messages: list[str] = []
    fake.batches = [LINES[:2]]
    fake.end = FAILED
    for noun in ("collector", "exporter", "reader"):
        fake.batches = [LINES[:2]]
        with pytest.raises(CollectionError) as caught:
            run(tmp_path / f"{noun}.txt", noun=noun)
        messages.append(str(caught.value))
    assert [m.split()[1] for m in messages] == ["collector", "exporter", "reader"]
