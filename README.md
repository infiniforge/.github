# InfiniForge organization documentation

This repository is the authoritative home for the cross-repository ecosystem manifest. The manifest describes component ownership, released versions where verifiable, library dependency relationships, public documentation, and implemented interoperability contracts.

- [Component manifest](ecosystem.json): machine-readable source for the ecosystem map.
- [Generated ecosystem map](docs/ECOSYSTEM.md): shared document copied into every component repository.
- [Documentation index](docs/README.md): validation, generation, release, and synchronization entry points.
- [Synchronization workflow](.github/workflows/ecosystem-docs.yml): validates the manifest and opens reviewable pull requests when component copies are stale.

`docs/ECOSYSTEM.md` in component repositories is generated. Update the manifest and regenerate it; do not edit component copies directly. Build dependency declarations and pins remain authoritative in each component's own Gradle/package metadata, dependency lock file, or submodule gitlink.
