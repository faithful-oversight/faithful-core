# Changelog

All notable changes to this project are recorded in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-11-21

### Fixed

- `write_files` checks the files that `remove` names against `protect`, as it already checked the files it writes. Before, with `force`, a protected file listed as stale was deleted ([#3](https://github.com/faithful-oversight/faithful-core/issues/3)).

### Changed

- The README, limitations and threat model name every network path: the WinRM transport and the Vault, AWS Secrets Manager, and Azure Key Vault secret providers, each used only when a product asks for it ([#4](https://github.com/faithful-oversight/faithful-core/issues/4)).
- The API page says `Target` does not check its fields.
- CI's downstream job checks that each product runs the core under test, and warns when a product does not depend on core yet.

## [0.1.0] - 2026-11-21

### Added

- Project foundation: license, documentation, contribution and security policies, continuous integration, and release pipeline.
- `faithful_core.errors`: `FaithfulError` and the four errors a tool reports, `InputError`, `CollectionError`, `UsageError`, and `OutputError`.
- `faithful_core.exitcodes`: `ExitCode`, with the exit codes every tool uses.
- `faithful_core.safety`: `visible`, `csv_cell`, `neutralize_formula`, `escape_markdown`, `terminal`, `terminal_line`, and `command_line`, which make untrusted text safe for each output.
- `faithful_core.clock`: `date_and_time` and `now`, which honors `SOURCE_DATE_EPOCH`.
- `faithful_core.console`: `prepare`, `say`, `finish`, and `stdout_closed`, which keep a closed pipe or an unencodable character from changing an exit code.
- `faithful_core.xmlsafe`: `parse` and its limits, which refuse a `DOCTYPE` and bound size, depth, and element count.
- `faithful_core.files`: `write_files`, `refuse_aliases`, and `copy_new`, which publish files atomically and refuse to replace a file the tool reads or write inside a folder it reads.
- `faithful_core.render`: `CSP`, `html_text`, `plural`, `md_text`, `md_table`, and `json_dump`.
- `faithful_core.collect.names`: `server_name`, `account_name`, and `install_hint`.
- `faithful_core.collect.secrets`: `resolve`, `redact`, `remember`, `REDACTED`, and `PROVIDERS`.
- `faithful_core.collect.script`: `ScriptResource`, which loads a packaged PowerShell script.
- `faithful_core.collect.winrm`: `Target`, `settings`, `client`, `drain`, `collect`, `publish_file`, and the `Sink` protocol.
- The optional extra `winrm`, which installs `pypsrp`.
- A test that checks the public names against the documented list, and that no message names a product.
