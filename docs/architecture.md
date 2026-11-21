# Architecture

## Shape of the library

faithful-core is a Python library with no command-line tool. Each module does one job, and the modules depend on each other as little as possible.

```text
errors, exitcodes          shared names every tool agrees on
safety, clock, render      pure functions: text in, text out
console                    printing that cannot change an exit code
xmlsafe                    untrusted XML in, element tree out
files                      a set of files out, atomically
collect.names, .script     small checks and a script loader
collect.secrets            a secret reference in, a secret out, and redaction
collect.winrm              the transport settings and the collection loop
```

`collect.winrm` uses `collect.secrets` and `files`. `files` uses `errors`. `render` uses `safety`. No other module imports a sibling.

## Rules the design follows

- **No runtime dependencies.** The library uses the standard library only. The WinRM transport needs `pypsrp`, which is an optional extra and is imported when it is first used. Each secret provider's package is imported the same way.
- **Products keep their product logic.** The library holds what must behave the same everywhere. Report content, input formats, manifests, command-line options, and PowerShell scripts stay in each product.
- **Parameters, not product names.** A product passes what differs: a temporary-file slug, a noun for messages, an install hint, a flag name. No message or docstring names a product.
- **Unsafe input stays visible.** Output that people read shows invisible and reordering characters as escapes. Machine-readable output keeps exact values.
- **Failures never change a decided exit code.** Printing, closing a pipe, and cleaning up after a failed collection do not raise a second error.
- **A refusal is the safe answer.** When the file system cannot say whether a target is a protected file, the guard refuses.
- **Public means documented.** Every module defines `__all__`, and a test checks it against [the API page](api.md).

## Packaging

- Python package on PyPI: `faithful-core`, with the import name `faithful_core`.
- The package is typed. It ships a `py.typed` marker.
- The extra `winrm` installs `pypsrp`.
