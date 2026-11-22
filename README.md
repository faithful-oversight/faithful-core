# faithful-core

**Shared foundation library.** The shared, tested foundation of the Faithful Oversight tools: safe output, atomic file publishing, console handling, and the WinRM collection plumbing.

[![CI](https://github.com/faithful-oversight/faithful-core/actions/workflows/ci.yml/badge.svg)](https://github.com/faithful-oversight/faithful-core/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Status: early.** The first release, 0.1.0, is on PyPI. Read the stability promise below before you depend on it.

## What it is

*faithful-core* is the common base every Faithful Oversight tool builds on. It holds the code that must behave the same in every tool, so that each fix and each test lives in one place.

It has no command-line tool of its own, and it has no runtime dependencies. Its foundation modules never use the network. Two parts can, and only when a tool asks for them: the WinRM transport, and the Vault, AWS Secrets Manager, and Azure Key Vault secret providers. Those providers use their own SDKs, which the tool installs, and each SDK's usual way of finding credentials. The library sends no telemetry.

## Who uses it

The Faithful Oversight tools: pakad, toledot, mishpat, shaar, merilo, and gvul. You can use it in your own tools too. The license allows it.

## What is in it

| Module | What it does |
| --- | --- |
| `faithful_core.errors` | One base error, `FaithfulError`, and the four errors a tool reports to its user. |
| `faithful_core.exitcodes` | The exit codes every tool uses. |
| `faithful_core.safety` | Makes untrusted text safe for a terminal, a CSV file, and Markdown. |
| `faithful_core.clock` | Writes times the same way on every platform, and gives a repeatable report time. |
| `faithful_core.console` | Prints without letting a closed pipe or a narrow terminal change an exit code. |
| `faithful_core.xmlsafe` | Parses untrusted XML with limits on size, depth, and element count. |
| `faithful_core.files` | Publishes a set of files atomically, and refuses to replace a file the tool reads. |
| `faithful_core.render` | Small helpers for HTML, Markdown, and JSON reports. |
| `faithful_core.collect.names` | Checks server and account names. Writes install hints. |
| `faithful_core.collect.secrets` | Fetches a secret from a variable, a file, a keyring, Vault, AWS, or Azure. Removes it from text. |
| `faithful_core.collect.script` | Loads a PowerShell script that a tool ships as package data. |
| `faithful_core.collect.winrm` | The WinRM transport settings and the collection loop. |

[docs/api.md](docs/api.md) describes every name.

## Stability promise

- The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- The names listed in [docs/api.md](docs/api.md) are the public interface. A breaking change to one of them needs a new major version. While the version is below 1.0.0, a minor version can break them, and the changelog says so.
- Anything that starts with an underscore is private. It can change in any release.
- Messages are for people. Their wording can change in any release, so do not match on it.
- Exit code values and the `FaithfulError` hierarchy are part of the public interface.

## Installation

```shell
pip install faithful-core
```

The WinRM transport needs `pypsrp`. It is an optional extra:

```shell
pip install "faithful-core[winrm]"
```

To try unreleased changes, install the development version from GitHub:

```shell
pip install git+https://github.com/faithful-oversight/faithful-core
```

To work from source, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage

```python
from pathlib import Path

from faithful_core.files import write_files
from faithful_core.render import md_table
from faithful_core.safety import terminal_line

rows = [["alice", "=1+1"], ["bob", "line one\nline two"]]
report = "\n".join(md_table(("Name", "Note"), rows)) + "\n"

written = write_files(
    Path("report"),
    {"report.md": report},
    force=False,
    slug="example",
)
print(terminal_line(str(written[0])))
```

## Documentation

- [API](docs/api.md)
- [Architecture](docs/architecture.md)
- [Threat model](docs/threat-model.md)
- [Limitations](docs/limitations.md)
- [Releasing](docs/releasing.md)
- [Architecture decision records](docs/adr/)

## Security

Please do not report security problems in public issues. See [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md) first.

## License

Copyright 2026 Faithful Oversight, LLC. Licensed under the [Apache License, Version 2.0](LICENSE).
