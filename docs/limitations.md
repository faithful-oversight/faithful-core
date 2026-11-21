# Limitations

faithful-core is honest about what it cannot do.

## Out of scope

The library does not:

- Ship a command-line tool of its own.
- Use the network, except the WinRM transport that a product asks for.
- Hold product logic, report formats, or PowerShell scripts. Those stay in each product.
- Define a manifest format. The products write different manifests, and each keeps its own.

## Limits of the guarantees

- **Atomic publishing is not crash-proof.** A crash or power loss in the middle of publishing can leave a mix of old and new files, and `.<slug>-old-*` backups. On a file system without hard links, a file is visible while it is written. A manifest that lists the size and SHA-256 of every file makes such a set detectable.
- **One writer per directory.** Two processes that write to the same output directory at once can remove or restore each other's files.
- **The alias guard depends on the file system.** It compares files by device and inode after links are resolved. When the file system cannot answer, the guard refuses. It cannot see a file that another process swaps in after the check.
- **Redaction knows only the secrets it has seen.** `redact` removes a secret that `resolve` or `remember` registered, in its common encoded forms. It cannot remove a secret that was never registered, or one that a library transforms in an unusual way.
- **XML limits bound memory, not time.** `xmlsafe` refuses a `DOCTYPE`, deep nesting, large files, and many elements. A document within those limits can still take time to parse.
- **Terminal safety is about text, not terminals.** `terminal` and `terminal_line` escape control and invisible characters. They do not know what a particular terminal does with the rest.
- **The WinRM transport is tested with a stand-in.** The tests replay chosen output through a fake `pypsrp`, and a few tests use the real transport classes when the `winrm` extra is installed. No test connects to a real Windows server.
