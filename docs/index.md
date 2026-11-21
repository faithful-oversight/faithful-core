# faithful-core documentation

faithful-core is the shared foundation of the Faithful Oversight tools. It holds the code that must behave the same in every tool: safe output, atomic file publishing, console handling, and the WinRM collection plumbing.

## Start here

- [API](api.md): every public name, one section per module.
- [Limitations](limitations.md): what the library does not do.

## Design

- [Architecture](architecture.md): how the library is built and the rules the design follows.
- [Threat model](threat-model.md): what the library protects, the threats, and the controls.
- [Releasing](releasing.md): how releases are made and verified.
- [Architecture decision records](adr/index.md): significant decisions and the reasons for them.
