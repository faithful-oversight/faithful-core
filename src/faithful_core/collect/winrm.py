# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Run a packaged PowerShell script on a Windows server over PowerShell remoting.

The script is sent to the server and run there with ``-ToPipeline``. Its lines stream back
to a *sink* that the product supplies. The sink checks each line as it comes, keeps the
lines in a private file next to the destination, and publishes that file only after the
script's end line checks out. A partial file is never left behind.

What the lines hold, and how the end line is checked, belong to the product. This module
holds what the products share: the transport settings, the secret handling, the loop that
drains the output, and the rule that every failure discards the sink.

Transport security is not optional. HTTPS (port 5986) always verifies the server's
certificate against the system's roots or the CA file. Plain HTTP (port 5985) is accepted
only with Kerberos, Negotiate, or NTLM message encryption required, which ``pypsrp`` then
enforces. Basic and CredSSP authentication are not offered.

``pypsrp`` is an optional dependency. It is imported when :func:`client` is first called,
so importing this module needs nothing but the standard library.
"""

from __future__ import annotations

import contextlib
import importlib
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from faithful_core.collect.secrets import redact, remember
from faithful_core.errors import CollectionError, OutputError
from faithful_core.files import copy_new, refuse_aliases

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = [
    "AUTHS",
    "POLL_SECONDS",
    "TRANSPORTS",
    "Sink",
    "Target",
    "client",
    "collect",
    "drain",
    "publish_file",
    "settings",
]

AUTHS = ("kerberos", "negotiate", "ntlm")
TRANSPORTS = ("https", "http")
POLL_SECONDS = 5
"""How long one wait for output lasts before the idle timeout is checked."""

R_co = TypeVar("R_co", covariant=True)
R = TypeVar("R")


@dataclass(frozen=True)
class Target:
    r"""Where and how to connect.

    Attributes:
        server: The server's fully qualified DNS name.
        auth: One of :data:`AUTHS`.
        username: ``DOMAIN\\user``, or ``None`` to use the current Kerberos ticket.
        secret: The password, already resolved, or ``None``.
        transport: ``https`` or ``http`` (with message encryption).
        port: The port, or ``None`` for 5986 or 5985.
        ca_file: A PEM file of certificate authorities to trust for HTTPS.
        connect_timeout: Seconds to wait for the connection.
        idle_timeout: Seconds without output after which collection stops.
    """

    server: str
    auth: str
    username: str | None = None
    secret: str | None = field(default=None, repr=False)
    transport: str = "https"
    port: int | None = None
    ca_file: Path | None = None
    connect_timeout: int = 30
    idle_timeout: int = 600


class Sink(Protocol[R_co]):
    """What :func:`collect` needs from a product's sink.

    The sink is created by the product, before :func:`collect` is called, for one
    destination. :func:`collect` then owns it: it calls :meth:`discard` on every failure,
    and :meth:`finish` and :meth:`publish` on success.
    """

    @property
    def ended(self) -> bool:
        """Whether the script's end line has arrived."""
        ...

    def take(self, item: object) -> None:
        """Check one item of output and keep it, or raise :class:`CollectionError`."""
        ...

    def finish(self) -> R_co:
        """Check the end line against what arrived and return what the product reports.

        Raises:
            CollectionError: The stream ended without its end line, or does not match it.
        """
        ...

    def publish(self, *, force: bool) -> None:
        """Put the checked file at the destination; an existing file needs ``force``."""
        ...

    def discard(self) -> None:
        """Remove the private file. This must not raise."""
        ...


def settings(target: Target) -> dict[str, Any]:
    """Return the WSMan settings for a target, refusing any insecure combination.

    Raises:
        CollectionError: The authentication or transport is not one this module offers.
    """
    if target.auth not in AUTHS or target.transport not in TRANSPORTS:
        msg = f"--auth must be one of {', '.join(AUTHS)} over https or encrypted http"
        raise CollectionError(msg)
    https = target.transport == "https"
    if target.ca_file is not None and not https:
        msg = "--ca-file applies to https only"
        raise CollectionError(msg)
    return {
        "server": target.server,
        "port": target.port or (5986 if https else 5985),
        "ssl": https,
        "auth": target.auth,
        "username": target.username,
        "password": target.secret,
        # A path is a CA bundle to verify against; True uses the system's roots.
        # There is no setting that turns verification off.
        "cert_validation": str(target.ca_file) if target.ca_file else True,
        "encryption": "auto" if https else "always",
        "connection_timeout": target.connect_timeout,
        "operation_timeout": POLL_SECONDS,
        "read_timeout": POLL_SECONDS + 30,
    }


def client(hint: str) -> tuple[Any, Any, Any, int]:
    """Import pypsrp's WSMan, RunspacePool, and PowerShell, and its running state.

    Args:
        hint: The command that installs the product with its remoting extra. It is shown
            when ``pypsrp`` is missing.

    Raises:
        CollectionError: ``pypsrp`` is not installed.
    """
    try:
        wsman = importlib.import_module("pypsrp.wsman")
        powershell = importlib.import_module("pypsrp.powershell")
        objects = importlib.import_module("pypsrp.complex_objects")
    except ImportError:
        msg = f"remote collection needs pypsrp; install it with: {hint}"
        raise CollectionError(msg) from None
    running: int = objects.PSInvocationState.RUNNING
    return wsman.WSMan, powershell.RunspacePool, powershell.PowerShell, running


def publish_file(temp: Path, destination: Path, *, force: bool) -> None:
    """Put a finished private file in place without following a link or clobbering.

    A product's sink can call this from its ``publish`` method. The temporary file is
    consumed. Without ``force`` an existing name, even a dangling link, is never replaced.

    Raises:
        CollectionError: The destination exists and ``force`` is off, or cannot be written.
    """
    if force:
        try:
            temp.replace(destination)
        except OSError as exc:
            msg = f"cannot write {destination}: {exc.strerror or exc}"
            raise CollectionError(msg) from exc
        return
    try:
        try:
            os.link(temp, destination)
        except FileExistsError:
            raise
        except OSError:
            # No hard links here (FAT, exFAT, some network shares): create the name
            # exclusively and copy. A failed copy removes what it created.
            copy_new(temp, destination)
    except FileExistsError:
        msg = f"{destination} already exists; pass --force to replace it"
        raise CollectionError(msg) from None
    except OSError as exc:
        msg = f"cannot write {destination}: {exc.strerror or exc}"
        raise CollectionError(msg) from exc
    temp.unlink()


def _keep_read_files(destination: Path, target: Target) -> None:
    """Refuse a destination that is a file the collection reads, even with ``force``."""
    if target.ca_file is None:
        return
    try:
        refuse_aliases([destination], [("CA file", target.ca_file)])
    except OutputError as exc:
        raise CollectionError(str(exc)) from None


def _refuse_destination(destination: Path, target: Target, *, force: bool) -> None:
    """Stop before connecting when the destination is a file read or one that exists."""
    _keep_read_files(destination, target)
    if os.path.lexists(destination) and not force:
        msg = f"{destination} already exists; pass --force to replace it"
        raise CollectionError(msg)


def collect(  # noqa: PLR0913 - one argument per collection choice
    target: Target,
    script: str,
    script_parameters: dict[str, Any],
    destination: Path,
    *,
    sink: Sink[R],
    noun: str,
    hint: str,
    force: bool,
    clock: Callable[[], float] = time.monotonic,
) -> R:
    """Run the script on the target and publish what it sent at ``destination``.

    Args:
        target: Where and how to connect.
        script: The PowerShell script text.
        script_parameters: The script's parameters.
        destination: The file to publish. It must not be a file the collection reads.
        sink: The product's sink for ``destination``. It is discarded on every failure.
        noun: What the script is called in messages, such as ``collector`` or ``exporter``.
        hint: The command that installs the product with its remoting extra.
        force: Replace an existing destination.
        clock: A monotonic clock, replaced in tests.

    Returns:
        What ``sink.finish()`` returned.

    Raises:
        CollectionError: The connection, authentication, or collection failed, or what
            arrived does not match the script's end line. Every message has the secret
            removed, and no partial file is left.
    """
    if target.secret:
        remember(target.secret)
    try:
        _refuse_destination(destination, target, force=force)
        wsman_class, pool_class, powershell_class, running = client(hint)
        with wsman_class(**settings(target)) as wsman, pool_class(wsman) as pool:
            shell = powershell_class(pool)
            shell.add_script(script)
            shell.add_parameters(script_parameters)
            shell.begin_invoke()
            drain(shell, sink, running, target.idle_timeout, clock, noun=noun)
            _check_failed(shell, sink, target.server, noun)
        result = sink.finish()
        _keep_read_files(destination, target)  # checked again, after the long wait
        sink.publish(force=force)
    except CollectionError as exc:
        sink.discard()
        raise CollectionError(redact(str(exc))) from None
    except Exception as exc:  # noqa: BLE001 - any library error, made safe to show
        sink.discard()
        text = redact(str(exc)) or type(exc).__name__
        msg = f"remote collection from {target.server} failed: {text}"
        raise CollectionError(msg) from None
    except BaseException:
        sink.discard()  # an interrupt must not leave the private file behind
        raise
    return result


def _check_failed(shell: Any, sink: Sink[Any], server: str, noun: str) -> None:
    """Report the script's own error when it stopped before its end line."""
    if not sink.ended and shell.had_errors:
        errors = [str(error) for error in getattr(shell.streams, "error", [])]
        reason = errors[0] if errors else "the script stopped with an error"
        msg = f"the {noun} failed on {server}: {reason}"
        raise CollectionError(msg)


def drain(  # noqa: PLR0913 - the loop needs the shell, the sink, and the three limits
    shell: Any,
    sink: Sink[Any],
    running_state: int,
    idle_timeout: int,
    clock: Callable[[], float],
    *,
    noun: str,
) -> None:
    """Take output as it arrives until the script ends, or stop it when it stalls.

    Raises:
        CollectionError: Nothing arrived for ``idle_timeout`` seconds. The script is
            stopped, as far as the server allows.
    """
    last = clock()
    while True:
        running = shell.state == running_state
        if running:
            shell.poll_invoke(timeout=POLL_SECONDS)
        output = shell.output
        if output:
            for item in output:
                sink.take(item)
            output.clear()
            last = clock()
        if not running:
            return
        if clock() - last > idle_timeout:
            with contextlib.suppress(Exception):
                shell.stop()
            msg = f"the {noun} sent nothing for {idle_timeout} seconds and was stopped"
            raise CollectionError(msg)
