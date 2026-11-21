# Threat model

> **Status: initial.** This model covers the library as first released. Review it whenever a module, an output rule, or a dependency changes.

## What the library protects

- **The operator's data.** Inputs are values and files that a Faithful Oversight tool passes to it. They can hold sensitive account, group, and configuration details.
- **Secrets.** The library fetches passwords for remote collection. They must not reach output, messages, or logs.
- **The integrity of results.** Reviewers and assessors rely on the files a tool publishes as evidence. The library must not replace a file the tool reads.
- **The operator's machine.** The library processes text and XML that may come from systems the operator does not fully trust.
- **The supply chain.** Every Faithful Oversight tool installs this library, so a flaw or a tampered release reaches all of them.

## Trust boundaries

1. Text, XML, and names enter the library from a tool, which got them from input files and the command line. They are untrusted.
2. Output text and files leave the library and are opened in terminals, browsers, spreadsheets, and review systems.
3. WinRM traffic crosses the network to a Windows server.
4. Release artifacts leave the build pipeline and are installed by users.

## Threats and controls (STRIDE)

The **Status** column uses three values. **In place** means the repository enforces it today. **Planned** means it is a design requirement for features not yet built. **Needs settings** means it depends on repository settings applied outside the code.

| Category | Threat | Control | Status |
| --- | --- | --- | --- |
| Spoofing | A tampered release artifact is installed in place of the real one. | Releases are built only by the release workflow from a commit on `main`, with a published `SHA256SUMS` file and a software bill of materials. Build provenance attestations are added once the repository is public. | In place (attestations when public) |
| Spoofing | A WinRM client talks to a server that is not the one named. | HTTPS always verifies the certificate against the system roots or a CA file. No setting turns verification off. Server names must be fully qualified DNS names, never addresses. | In place |
| Tampering | A malicious change enters the code base. | Pull requests only, a required passing check, resolved conversations, no force pushes to `main`, signed-off commits, and actions pinned to full commit hashes. | In place (branch rules need settings) |
| Tampering | An output file replaces a file the tool reads, such as evidence or a CA file. | `refuse_aliases` compares files after links, `..`, and spelling are resolved, and refuses a target inside a protected folder. It refuses when the file system cannot answer. | In place |
| Tampering | A crash or a second writer leaves a mix of old and new output. | Atomic staged publishing with rollback. The limits are stated in [Limitations](limitations.md). | In place, with stated limits |
| Tampering | A collection that is cut short or damaged is published as complete. | A product's sink checks every line and the end line. Nothing is published until `finish` passes, and a failure discards the private file, an interrupt included. | In place |
| Repudiation | A user cannot show which inputs produced a report. | A product records hashes in its manifest. The library publishes the manifest last, when the product asks for that order. | In place |
| Information disclosure | A secret appears in a message, an error, or a log. | `redact` removes every remembered secret, in its common encoded forms, from every collection message. Library errors are replaced by a message that holds only their type when they carry no text. | In place |
| Information disclosure | Output files are readable by other users. | New files are private to the current user on Linux and macOS. | In place |
| Information disclosure | The library sends data over the network. | The only network code is the WinRM transport that a product asks for. No telemetry. | In place |
| Denial of service | Oversized or deeply nested XML exhausts memory or time. | `xmlsafe` limits size, depth, and element count, and refuses a `DOCTYPE`. The expat parser does not expand entities. | In place |
| Denial of service | A stalled server holds a collection open. | An idle timeout stops the script and discards the private file. | In place |
| Elevation of privilege | Input text runs as code in a terminal, a spreadsheet, Markdown, or HTML. | `terminal` escapes control characters. `csv_cell` neutralizes formulas. `escape_markdown` and `html_text` escape markup and hidden characters. | In place |
| Elevation of privilege | A compromised dependency or build step runs with broad permissions. | No runtime dependencies. Locked versions, vulnerability and license scanning, least-privilege workflow tokens, and workflow security analysis with zizmor. | In place |

## Residual risks

- The library cannot make a tool correct. A tool that skips `csv_cell` or `html_text` loses the protection.
- Checksums and attestations protect users only if they verify them. [Releasing](releasing.md) shows how.
