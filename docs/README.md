# InfiniForge ecosystem documentation index

- [ECOSYSTEM.md](ECOSYSTEM.md): generated overview of all applications, shared libraries, dependencies, ownership boundaries, released versions, and implemented inter-app contracts.
- [../ecosystem.json](../ecosystem.json): authoritative structured source. Edit this file; do not edit generated copies.
- [../README.md](../README.md): role of the organization-level documentation repository and authoritative links.
- [../AGENTS.md](../AGENTS.md): agent workflow for updating the manifest and generator.
- [../scripts/ecosystem.py](../scripts/ecosystem.py): validates IDs, references, versions, dependency cycles and locks, API documentation paths, local Markdown links, and generated-document freshness.
- [synchronization.md](synchronization.md): workflow prerequisites, token permissions, loop prevention, and local commands.
- [../.github/workflows/ecosystem-docs.yml](../.github/workflows/ecosystem-docs.yml): validates and creates reviewable pull requests to update stale component copies.
