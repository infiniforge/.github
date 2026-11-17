# Ecosystem documentation synchronization

The authoritative manifest and generator live in the `infiniforge/.github` organization repository. The workflow validates the manifest and central generated output, then checks each component repository. If `docs/ECOSYSTEM.md` differs, it updates a reserved bot branch and opens or refreshes a pull request. It does not merge pull requests or change application source/build files.

## Required repository secret

Add `INFINIFORGE_SYNC_TOKEN` as an Actions secret in the `infiniforge/.github` repository (Settings → Secrets and variables → Actions), or as an organization secret available to that repository. Use a GitHub App installation token or fine-grained token with **Contents: read/write** and **Pull requests: read/write** on all participating repositories. The workflow uses it only to clone component repositories, push the reserved `chore/sync-ecosystem-docs` branch, and create/update reviewable pull requests.

The workflow runs when the manifest, generator, or synchronization workflow changes on `main`, or by manual dispatch from `main`. Changes made in component repositories do not trigger it, which prevents synchronization loops. A missing secret causes synchronization to stop with a clear setup message; manifest validation still runs independently.

## Local commands

From this repository:

```sh
python3 scripts/ecosystem.py validate
python3 scripts/ecosystem.py render --output docs/ECOSYSTEM.md
python3 scripts/ecosystem.py check --file docs/ECOSYSTEM.md
python3 scripts/ecosystem.py validate-repo --component infinimedia --root /path/to/infinimedia --links --generated
python3 scripts/ecosystem.py check-links --root /path/to/repository
```

`validate-repo` verifies local API-document paths, the declared component version against build metadata, and the manifest dependency IDs against the component's source lock. `--links` checks local Markdown link targets. Links into an uninitialized Git submodule are deferred because the owning component is validated separately in the same synchronization run. External links are not fetched over the network; repository references in the manifest are checked against the organization naming convention.
