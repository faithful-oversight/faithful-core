# API

This page lists every public name in `faithful-core`. A name is public when this page lists it. Anything that starts with an underscore is private and can change in any release.

Every module defines `__all__` with its public names. A test checks that `__all__` and this page agree.

Messages are for people. Do not match on their wording.

## errors

`faithful_core.errors` holds the exceptions that a tool reports to its user.

| Name | Meaning |
| --- | --- |
| `FaithfulError` | The base class. Catch it once in the tool's `main`. |
| `InputError` | An input file or configuration cannot be read or has the wrong shape. |
| `CollectionError` | Live collection could not connect, authenticate, or read what it needs. |
| `UsageError` | The command's options do not fit together, so nothing was attempted. |
| `OutputError` | Output files cannot be written, or writing them would replace a file the tool reads. |

All four subclass `FaithfulError`. A product can make its own base error an alias of `FaithfulError`, and add classes of its own.

## exitcodes

`faithful_core.exitcodes.ExitCode` is an `IntEnum`. The values are part of the public interface.

| Name | Value | Meaning |
| --- | --- | --- |
| `OK` | 0 | Success with no findings. |
| `FINDINGS` | 1 | The tool reported findings. |
| `USAGE` | 2 | The command was used incorrectly. |
| `INPUT_ERROR` | 3 | The input could not be processed. |
| `INTERNAL_ERROR` | 4 | The tool failed in a way it did not expect. |

## safety

`faithful_core.safety` makes untrusted values safe for each output format. People-facing output shows invisible and reordering characters as visible escapes, so a reader sees what the data really contains.

| Name | What it does |
| --- | --- |
| `visible(value)` | Replaces control, format, separator, and look-alike space characters with escapes such as `‮`. Tab and line breaks stay. |
| `csv_cell(value)` | Makes a value safe for a spreadsheet cell. It applies `visible`, then `neutralize_formula`. |
| `neutralize_formula(value)` | Adds a leading apostrophe to a value that a spreadsheet could read as a formula. A plain negative number stays a number. |
| `FORMULA_TRIGGERS` | The leading characters that count as the start of a formula. |
| `escape_markdown(value)` | Escapes text for a Markdown table cell or paragraph. Line breaks become a visible arrow. |
| `terminal(value)` | Makes text safe to print. Line feeds stay. A carriage return and a tab become escapes. |
| `terminal_line(value)` | Like `terminal`, and a line feed also becomes `\n`. Use it for every value placed inside one line of output. |
| `command_line(*parts)` | Quotes a command for copying into this platform's usual shell. |

## clock

`faithful_core.clock` writes times as text the same way on every platform.

| Name | What it does |
| --- | --- |
| `date_and_time(moment, separator="T")` | Returns `YYYY-MM-DD` and `HH:MM:SS` joined by `separator`. The year always has four digits. The time zone is not converted. |
| `now()` | Returns the report time as an aware UTC `datetime` with no microseconds. When `SOURCE_DATE_EPOCH` holds ASCII digits that make a valid time, that time is returned, so a report can be repeated byte for byte. |

## console

`faithful_core.console` prints without letting a print failure change an exit code that is already decided. A command decides its exit code first, prints through `say`, and calls `finish` at the end.

| Name | What it does |
| --- | --- |
| `prepare()` | Call once at the start. Makes the standard streams write a character they cannot encode as a backslash escape. It also starts printing again after an earlier closed pipe in the same process. |
| `say(text="", *, error=False, end="\n")` | Prints `text`, to standard error with `error=True`. A closed pipe is never an error. After standard output closes, later calls to it do nothing. |
| `finish()` | Flushes both streams. A closed pipe found now is handled like one found while printing. |
| `stdout_closed()` | Stops printing to standard output and points it at the null device, so the flush at interpreter shutdown cannot fail. `say` and `finish` call it. You rarely need to. |

## xmlsafe

`faithful_core.xmlsafe` parses XML from untrusted files with the standard library's expat parser.

- A `DOCTYPE`, and so every entity declaration, is refused. Nothing is fetched or expanded.
- Nesting deeper than `MAX_DEPTH` is refused.
- A file larger than `MAX_BYTES` is refused before it is decoded.
- At most `MAX_ELEMENTS` elements are held at once.
- The declared encoding is ignored. The bytes are decoded from the byte order mark, or as UTF-8, or as UTF-16.

| Name | What it does |
| --- | --- |
| `parse(data, *, max_bytes=None, max_elements=MAX_ELEMENTS, max_total=None, take=None)` | Returns the root `Element`. Raises `XmlError` for anything it refuses. With `take`, complete elements at a path are handed to a function and dropped, so a large worksheet is read in constant memory. |
| `decode(data)` | Decodes the bytes to text, by the last rule in the list. |
| `split(tag)` | Splits `{uri}local` into `(uri, local)`. |
| `XmlError` | A `ValueError` for bytes that are not XML this library will read. |
| `Take` | The type of the `take` argument: a path of local names, and a function. |
| `MAX_DEPTH`, `MAX_BYTES`, `MAX_ELEMENTS` | The default limits. |

## files

`faithful_core.files` publishes a set of output files together, privately, and without clobbering. The module docstring states every guarantee exactly. The main ones:

- Files go to private temporary files first, then under their final names in the order given.
- Without `force`, an existing file is never replaced, even if it appears after the first check.
- With `force`, the old files are moved aside first. If a step fails, the old set comes back.
- A target that is a protected file, or is inside a protected folder, is refused with or without `force`. When the file system cannot answer, the answer is a refusal.
- Messages mention `--force`, the option name that every tool uses.

| Name | What it does |
| --- | --- |
| `write_files(directory, files, *, force, slug, protect=(), remove=())` | Publishes every file, or leaves the directory as it was. `files` maps names to `str` (encoded as UTF-8, with no newline translation) or `bytes`. `slug` names the temporary files `.<slug>-*.tmp` and `.<slug>-old-*.bak`. `protect` is `(role, path)` pairs. `remove` names files from an earlier run that this run does not write. With `force`, the plain files among them are removed in the same swap. Returns the written paths. Raises `OutputError`. |
| `refuse_aliases(targets, protect)` | Raises `OutputError` when a target is the same file as a protected path, or is inside a protected folder. A tool can call it before it starts slow work. `write_files` calls it for you when `protect` is given. |
| `copy_new(temp, target)` | Creates `target` from `temp` for file systems with no hard links. The name is created exclusively and removed again on failure. Raises `FileExistsError` if the name exists. |

## collect.names

`faithful_core.collect.names` checks the names given for remote collection. It checks them before any secret is fetched or any connection is made.

| Name | What it does |
| --- | --- |
| `server_name(server, *, flag="--server")` | Checks that `server` is a fully qualified DNS name, and returns it without a trailing dot. `flag` names the option in the message. Raises `CollectionError`. |
| `account_name(username)` | Checks a user name and returns it as `DOMAIN\user`. `None` stays `None`. Raises `CollectionError`. |
| `install_hint(distribution, *extras, source=None)` | Returns the command that installs `distribution` with `extras`. It gives one form for pipx and one for pip. With `source`, a git URL, the command installs from that repository. |

## collect.secrets

`faithful_core.collect.secrets` fetches a secret from where it is kept. A reference is `PROVIDER:LOCATION`.

| Provider | Location |
| --- | --- |
| `env` | `NAME`, an environment variable. |
| `file` | `PATH`, the first line of a file. |
| `keyring` | `SERVICE/USERNAME`, the operating system keychain. Needs `keyring`. |
| `vault` | `MOUNT/PATH#FIELD`, a Vault KV version 2 secret. Needs `hvac`. |
| `aws` | `SECRET_ID` or `SECRET_ID#FIELD`, AWS Secrets Manager. Needs `boto3`. |
| `azure` | `VAULT_NAME/SECRET_NAME`, Azure Key Vault. Needs the Azure packages. |

Each provider's package is imported only when its provider is used. The package is not a dependency of `faithful-core`.

| Name | What it does |
| --- | --- |
| `resolve(reference, *, hint, keep=())` | Returns the secret, and remembers it. `hint` says how to install the product with extras. When a provider's package is missing, the message uses `hint(*keep, extra)`. Raises `CollectionError`. |
| `redact(text)` | Removes every remembered secret from `text`, in its plain, URL-encoded, JSON-escaped, and `repr` forms. |
| `remember(secret)` | Adds a secret that was not resolved here, such as one given directly. |
| `REDACTED` | The text that replaces a secret. |
| `PROVIDERS` | The provider names. |
| `InstallHint` | The type of `hint`: a callable that takes extras and returns text. `functools.partial(install_hint, "faithful-example")` is one. |

## collect.script

`faithful_core.collect.script.ScriptResource(package, name, noun)` loads a PowerShell script from the `data` folder of a package. `noun` is what the script is called in messages, such as `collector`.

| Method | What it does |
| --- | --- |
| `text()` | Returns the script. It is pure ASCII, so Windows PowerShell 5.1 reads it the same as PowerShell 7. |
| `version()` | Returns the version from the line `$CollectorVersion = 'X.Y.Z'`. Raises `ValueError` if there is none. |

## collect.winrm

`faithful_core.collect.winrm` runs a packaged PowerShell script on a Windows server over PowerShell remoting. It needs the `winrm` extra, which installs `pypsrp`. The module imports `pypsrp` only when `client` is called.

Transport security is not optional. HTTPS always verifies the certificate. Plain HTTP is accepted only with message encryption required. Basic and CredSSP authentication are not offered. Messages name the options `--auth` and `--ca-file`, which every tool that collects remotely uses.

| Name | What it does |
| --- | --- |
| `Target` | A frozen dataclass: `server`, `auth`, `username`, `secret`, `transport`, `port`, `ca_file`, `connect_timeout`, `idle_timeout`. The secret is left out of its `repr`. It does not check its fields: call `server_name` and `account_name` on the values before you build one. |
| `AUTHS`, `TRANSPORTS` | The accepted authentication methods and transports. |
| `POLL_SECONDS` | How long one wait for output lasts. |
| `settings(target)` | Returns the WSMan settings, and refuses any insecure combination. |
| `client(hint)` | Imports the `pypsrp` classes. When `pypsrp` is missing, the message shows `hint`. |
| `drain(shell, sink, running_state, idle_timeout, clock, *, noun)` | Takes output as it arrives. Stops the script when it goes quiet. |
| `collect(target, script, script_parameters, destination, *, sink, noun, hint, force, clock=...)` | Runs the script and publishes what it sent. Returns what `sink.finish()` returned. |
| `publish_file(temp, destination, *, force)` | Puts a finished private file in place without following a link or clobbering. A sink can call it from `publish`. |
| `Sink` | The protocol a product's sink implements. |

A product supplies the sink. It checks each line, keeps the lines in a private file, and checks the end line. The product also keeps its own `parameters` function and its own result type.

| `Sink` member | Meaning |
| --- | --- |
| `ended` | Whether the end line has arrived. |
| `take(item)` | Checks and keeps one item. Raises `CollectionError`. |
| `finish()` | Checks the end line against what arrived. Returns what the product reports. |
| `publish(*, force)` | Puts the checked file at the destination. |
| `discard()` | Removes the private file. It must not raise. |

The product creates the sink, then calls `collect`. From then on `collect` owns it. It calls `discard` on every failure, including an interrupt, and removes the secret from every message. It also refuses a destination that is the CA file. It checks before connecting and checks again before publishing.

## render

`faithful_core.render` holds the helpers that every report renderer needs. The renderers stay in each product.

| Name | What it does |
| --- | --- |
| `CSP` | A content security policy for an HTML report: no scripts, no network, no forms. |
| `html_text(value)` | Makes a value safe in HTML text or a quoted attribute. |
| `plural(n, one, many=None)` | Returns `n` with the noun in the right number, such as `2 files`. |
| `md_text(value)` | Escapes a value for Markdown. It calls `escape_markdown` on `str(value)`. |
| `md_table(head, rows)` | Returns the lines of a Markdown table. The heading is written as given. Every cell is escaped. |
| `json_dump(value)` | Returns indented JSON that ends with a line feed. If the value holds a lone surrogate, the text is written again with JSON escapes so that it still encodes as UTF-8. |
