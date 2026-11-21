# core

**Shared foundation library.** The shared, tested foundation of the Faithful Oversight tools: safe output, atomic file publishing, console handling, and the WinRM collection plumbing.

[![CI](https://github.com/faithful-oversight/faithful-core/actions/workflows/ci.yml/badge.svg)](https://github.com/faithful-oversight/faithful-core/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> **Status: pre-release.** The repository holds the project foundation only. No feature is implemented yet, and nothing here is ready for production use.

## About the name

*core* (core). The common base every Faithful Oversight tool builds on.

## What it will do

- Neutralize untrusted text before it reaches a terminal, a CSV file, Markdown, or HTML.
- Publish a set of output files atomically, and refuse to overwrite a file the tool reads.
- Print without letting a closed pipe or a narrow terminal change an exit code.
- Parse XML safely, with limits on size, depth, and element count.
- Provide the shared WinRM collection plumbing: target settings, secret lookup, and the transport loop.

## What it will not do

- Ship a command-line tool of its own.
- Use the network, except the WinRM transport that a product asks for.
- Hold product logic, report formats, or PowerShell scripts. Those stay in each product.

See [docs/limitations.md](docs/limitations.md) for the full list.

## Design goals

- **Read-only.** The tool will never change the systems it examines.
- **Offline first.** Inputs will be exported files, with no network access required.
- **Explicit unknowns.** Every report will state what the tool could not see or verify.
- **Traceable findings.** Every finding will point back to its source record and the rule that produced it.
- **Synthetic test data only.** Fixtures are hand-made or generated. No real organization's data is ever committed.

## Installation

Not yet on PyPI. Until the first release, install the development version from GitHub:

```shell
pipx install git+https://github.com/faithful-oversight/faithful-core
pipx ensurepath
```

`pipx ensurepath` puts the `core` command on your PATH; run it once and open a new terminal. After the first release, the package will install with `pipx install faithful-core`.

To work from source, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage

```shell
core --version
```

## Documentation

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
