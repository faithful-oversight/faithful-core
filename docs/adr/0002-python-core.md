# 2. Python library with no runtime dependencies

- Status: accepted
- Date: 2026-11-21

## Context

The library is the base of six tools that administrators and assessors install. Every dependency of the library becomes a dependency of every tool, and a flaw in the supply chain would reach all of them.

## Decision

- Write the library in Python 3.11 or newer, fully typed and checked with mypy in strict mode.
- Use the standard library only. A feature that needs another package gets an optional extra, and the package is imported when the feature is first used. The `winrm` extra and the secret providers work this way.
- Keep the public interface small, documented, and covered by semantic versioning. Private names start with an underscore.
- Manage the environment and lock file with uv.

## Consequences

A tool that does not collect remotely installs nothing but this library. The WinRM transport can change its package without changing the public interface. A new runtime dependency needs a new decision record.
