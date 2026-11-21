#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
#
# Install the exact wheel in a directory into a clean environment and run it.
# CI and the release workflow both run this on the files they publish.
#
# Usage: scripts/smoke_test.sh <dist-directory>
#
# This library has no command. The smoke test imports the installed wheel and calls
# each module once, so a broken package cannot be released.

set -euo pipefail

dist="${1:?dist directory required}"
shopt -s nullglob
wheels=("$dist"/*.whl)
[[ ${#wheels[@]} -eq 1 ]] || { echo "expected exactly one wheel in $dist" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

uv venv --quiet "$work/venv"
uv pip install --quiet --python "$work/venv" --no-deps "${wheels[0]}"
if [[ -x "$work/venv/bin/python" ]]; then
  py="$work/venv/bin/python"
else
  py="$work/venv/Scripts/python.exe"
fi

# --- Library smoke test: import the installed wheel and call each module. ---
# Run from the clean directory with -I so the source tree is never on the path.
(
  cd "$work"
  "$py" -I - <<'PY'
import tempfile
from pathlib import Path

import faithful_core
from faithful_core import clock, files, render, safety, xmlsafe
from faithful_core.collect import names, secrets, winrm
from faithful_core.exitcodes import ExitCode

assert faithful_core.__version__ != "0.0.0+unknown", faithful_core.__version__
assert [int(code) for code in ExitCode] == [0, 1, 2, 3, 4]
assert safety.csv_cell("=1+1") == "'=1+1"
assert safety.terminal_line("a\nb") == "a\\nb"
assert clock.date_and_time(clock.now(), " ").count(" ") == 1
assert xmlsafe.parse(b"<a><b/></a>").tag == "a"
assert render.md_table(("a",), [["x|y"]])[2] == "| x\\|y |"
assert render.json_dump({"k": "\udc80"}).startswith("{")
assert names.server_name("dc01.corp.example") == "dc01.corp.example"
assert names.install_hint("faithful-example", "winrm").startswith("pipx install --force")
assert secrets.resolve("env:PATH", hint=lambda *extras: "")
assert winrm.settings(winrm.Target("dc01.corp.example", "kerberos"))["ssl"] is True
with tempfile.TemporaryDirectory() as folder:
    (written,) = files.write_files(Path(folder), {"a.txt": "text"}, force=False, slug="smoke")
    assert written.read_text(encoding="utf-8") == "text"
print("library smoke test passed")
PY
)

echo "smoke test passed: ${wheels[0]}"
