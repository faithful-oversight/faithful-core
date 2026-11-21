# 4. One shared foundation library for the tools

- Status: accepted
- Date: 2026-11-21

## Context

Six tools carried copies of the same modules: output safety, console handling, atomic file publishing, secret handling, and the WinRM transport. The copies had drifted apart. A fix in one copy did not reach the others, and the tests for the same code differed from tool to tool.

## Decision

- Move the modules that must behave the same in every tool into this library. One release holds the whole scope.
- Each tool keeps its product logic: report content, input formats, manifests, command-line options, and PowerShell scripts.
- Each tool pins an exact version of this library in its lock file.
- Differences between the old copies become parameters, such as a temporary-file slug, a noun for messages, and an install hint. No message names a product.
- Where the copies disagreed, the library takes the safer behavior. For example, the alias guard refuses when the file system cannot answer.

## Consequences

A fix and its tests live in one place. A change to this library reaches every tool, so its public interface follows semantic versioning and its tests run against the tools before a release. The library becomes a runtime dependency of every tool, which makes its own supply chain more important.
