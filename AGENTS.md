# InfiniForge organization documentation agent guide

This repository owns the central ecosystem manifest and the generator that produces shared ecosystem documentation. It does not own application or library source code.

## Before changing ecosystem metadata

1. Read `docs/ECOSYSTEM.md` and `docs/README.md`.
2. Verify component responsibilities, release records, dependency sources, and protocol behavior in the referenced component repositories.
3. Keep build dependency versions and commit pins authoritative in each component's build metadata and lock files; do not duplicate them here.
4. Keep library release versions independent from Android interoperability protocol versions.
5. Preserve the generated-copy workflow: updates are proposed as pull requests in participating repositories.
6. Update the manifest schema/generator and validation rules together when the source fields change.

## Documentation index

- `README.md`: purpose of this organization-level documentation repository.
- `ecosystem.json`: authoritative machine-readable inventory and protocol/version metadata.
- `docs/ECOSYSTEM.md`: generated human-readable ecosystem map.
- `docs/README.md`: index of this repository's documentation and maintenance commands.
- `scripts/ecosystem.py`: validation, deterministic generation, stale-copy checks, and local link checks.
- `.github/workflows/ecosystem-docs.yml`: validation and PR-based copy synchronization.
- `docs/synchronization.md`: required token permissions, workflow behavior, and local commands.
