#!/usr/bin/env python3
"""Validate the InfiniForge ecosystem manifest and render synchronized docs."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ecosystem.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)")


def fail(message: str) -> None:
    raise ValueError(message)


def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Cannot read manifest {path}: {exc}")


def validate_manifest(data: dict) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data.get("audited_on", ""))):
        errors.append("audited_on must be an ISO date")
    components = data.get("components")
    protocols = data.get("protocols")
    if not isinstance(components, list) or not isinstance(protocols, list):
        return errors + ["components and protocols must be arrays"]

    by_id: dict[str, dict] = {}
    for component in components:
        cid = component.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append("component has missing/invalid id")
            continue
        if cid in by_id:
            errors.append(f"duplicate component id: {cid}")
        by_id[cid] = component
        if component.get("kind") not in {"application", "library", "asset-repository"}:
            errors.append(f"{cid}: invalid kind")
        if component.get("status") not in {"active", "planned"}:
            errors.append(f"{cid}: invalid status")
        if component.get("build_status") not in {"standalone", "standalone-library", "planned", "asset-tools"}:
            errors.append(f"{cid}: invalid or missing build_status")
        if component.get("status") == "planned" and component.get("build_status") != "planned":
            errors.append(f"{cid}: planned components must declare build_status planned")
        if component.get("status") == "active" and component.get("kind") in {"application", "library"} and not component.get("declared_version"):
            errors.append(f"{cid}: active applications/libraries need an independently declared component version")
        repository = component.get("repository", "")
        expected = f"https://github.com/{data.get('organization')}/{cid}"
        if repository != expected:
            errors.append(f"{cid}: repository must be {expected}")
        if not component.get("purpose") or not component.get("responsibilities"):
            errors.append(f"{cid}: purpose and responsibilities are required")
        for key in ("released_version", "declared_version"):
            value = component.get(key)
            if value is not None and not SEMVER.fullmatch(str(value)):
                errors.append(f"{cid}: {key} must be SemVer or null")
        if component.get("released_version") and not component.get("release_url"):
            errors.append(f"{cid}: a released_version needs a release_url")
        if component.get("released_version") and component.get("latest_tag", "").removeprefix("v") != component.get("released_version"):
            errors.append(f"{cid}: released_version must match latest_tag")
        if component.get("latest_tag"):
            tag_version = str(component["latest_tag"]).removeprefix("v")
            if not SEMVER.fullmatch(tag_version):
                errors.append(f"{cid}: latest_tag must be vMAJOR.MINOR.PATCH")
        if (component.get("declared_version") is None) != (component.get("declared_version_source") is None):
            errors.append(f"{cid}: declared_version and its source must be set together")
        if not isinstance(component.get("dependencies"), list):
            errors.append(f"{cid}: dependencies must be an array")
        if not isinstance(component.get("integrations", []), list):
            errors.append(f"{cid}: integrations must be an array")
        for field in ("api_docs", "protocols"):
            if not isinstance(component.get(field), list):
                errors.append(f"{cid}: {field} must be an array")

    for cid, component in by_id.items():
        for dep in component.get("dependencies", []):
            if dep not in by_id:
                errors.append(f"{cid}: unknown dependency {dep}")
            if dep == cid:
                errors.append(f"{cid}: self dependency")
        for integration in component.get("integrations", []):
            if integration not in by_id:
                errors.append(f"{cid}: unknown integration {integration}")

    protocol_ids: set[str] = set()
    for protocol in protocols:
        pid = protocol.get("id")
        if not isinstance(pid, str) or not pid:
            errors.append("protocol has missing/invalid id")
            continue
        if pid in protocol_ids:
            errors.append(f"duplicate protocol id: {pid}")
        protocol_ids.add(pid)
        if protocol.get("version") is not None and not isinstance(protocol.get("version"), (str, int)):
            errors.append(f"{pid}: version must be a string, integer, or null")
        for field in ("implemented_by",):
            for cid in protocol.get(field, []):
                if cid not in by_id:
                    errors.append(f"{pid}: unknown implementing component {cid}")
        for field in ("request", "response", "errors", "compatibility", "fallback", "negotiation", "resource_identity"):
            if not protocol.get(field):
                errors.append(f"{pid}: missing {field} contract")

    for cid, component in by_id.items():
        for pid in component.get("protocols", []):
            if pid not in protocol_ids:
                errors.append(f"{cid}: unknown protocol {pid}")

    # The manifest records the locked source dependency closure. A cycle is still
    # an architectural cycle and is rejected; optional runtime integrations are
    # deliberately excluded from build dependency cycle checks.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(cid: str, trail: list[str]) -> None:
        if cid in visiting:
            errors.append("dependency cycle: " + " -> ".join(trail + [cid]))
            return
        if cid in visited:
            return
        visiting.add(cid)
        for dep in by_id[cid].get("dependencies", []):
            if dep in by_id:
                visit(dep, trail + [cid])
        visiting.remove(cid)
        visited.add(cid)

    for cid in by_id:
        visit(cid, [])

    policy = data.get("versioning_policy", {})
    for key in ("scheme", "meaning", "tag_convention", "release_record", "version_sources", "dependency_versions", "protocol_versions"):
        if not policy.get(key):
            errors.append(f"versioning_policy missing {key}")
    return errors


def component_link(component: dict, path: str | None = None) -> str:
    base = component["repository"]
    if path:
        return f"{base}/blob/main/{urllib.parse.quote(path, safe='/._-')}"
    return base


def version_label(component: dict) -> str:
    released = component.get("released_version")
    declared = component.get("declared_version")
    tag = component.get("latest_tag")
    bits: list[str] = []
    bits.append(f"released `{released}`" if released else "no published release verified")
    if declared:
        bits.append(f"build declares `{declared}`")
    elif component.get("status") == "planned":
        bits.append("not versioned yet")
    if tag:
        bits.append(f"tag `{tag}`")
    return "; ".join(bits)


def render(data: dict) -> str:
    by_id = {c["id"]: c for c in data["components"]}
    apps = [c for c in data["components"] if c["kind"] == "application"]
    libs = [c for c in data["components"] if c["kind"] == "library"]
    assets = [c for c in data["components"] if c["kind"] == "asset-repository"]
    standalone_apps = sum(c["kind"] == "application" and c.get("build_status") == "standalone" for c in data["components"])
    lines = [
        "# InfiniForge ecosystem",
        "",
        f"This file is generated from the authoritative [ecosystem manifest](https://github.com/infiniforge/.github/blob/main/ecosystem.json) (inventory checked {data['audited_on']}). Do not edit this copy; changes are synchronized from that repository through reviewable pull requests.",
        "",
        "InfiniForge is a set of independently buildable and released Android applications and reusable library repositories. Each app owns its application identity, UI, lifecycle, settings, user data, permissions, and standalone build. Libraries provide reusable APIs and do not make one application depend on another.",
        "",
        "## Component inventory",
        "",
        f"The inventory contains {len(apps)} applications ({standalone_apps} with standalone builds and {len(apps) - standalone_apps} planned placeholders), {len(libs)} shared libraries, and {len(assets)} canonical asset repository.",
        "",
    ]
    sections = [
        ("Applications", apps),
        ("Shared libraries", libs),
        ("Canonical assets", assets),
    ]
    for section_name, members in sections:
        lines += [f"### {section_name}", ""]
        for c in members:
            status = "planned placeholder" if c["status"] == "planned" else c["status"]
            build_label = {"standalone":"standalone app build", "standalone-library":"standalone library build", "planned":"no build yet", "asset-tools":"documented asset build"}[c["build_status"]]
            deps = c.get("dependencies", [])
            dep_links = ", ".join(f"[{d}]({by_id[d]['repository']})" for d in deps) if deps else "None declared"
            integrations = c.get("integrations", [])
            integration_text = ", ".join(f"[{x}]({by_id[x]['repository']})" for x in integrations) if integrations else "None recorded"
            api_docs = c.get("api_docs", [])
            docs = ", ".join(f"[{Path(path).name}]({component_link(c, path)})" for path in api_docs) if api_docs else "None published yet"
            exact_pins = f"[{c['dependency_source']}]({component_link(c, c['dependency_source'])})" if c.get("dependency_source") else "Use the component's Gradle/package metadata; no ecosystem source lock is declared."
            lines += [
                f"#### [{c['id']}]({c['repository']})",
                "",
                f"**State:** {status} · **Build:** {build_label} · **Versions:** {version_label(c)}",
                "",
                f"**Purpose:** {c['purpose']} {c['responsibilities']}",
                "",
                f"**Pinned source dependency closure:** {dep_links}",
                "",
                f"**Exact dependency pins:** {exact_pins}",
                "",
                f"**Optional/runtime integrations:** {integration_text}",
                "",
                f"**Public API and architecture documentation:** {docs}",
                "",
            ]
    lines += [
        "Exact dependency commits and package versions remain authoritative in each repository's Gradle/package metadata, source lock, or submodule gitlink. Dependency lists above identify ecosystem components in the locked source closure and can include transitive libraries. Optional integrations are runtime relationships, not build dependencies.",
        "",
        "## Responsibility boundaries and resource flow",
        "",
        "- **Applications** own their installable entry points and app-specific UI, state, data, and permissions. Infinifolder is the file manager and advanced storage companion, but it is optional. Infinimedia owns playback and playlists; Infiniscribe owns document viewing/editing; Infinikey owns its IME and its private layouts/themes. Canvas, Wave, Track, Launch, and Play are planned placeholders.",
        "- **Libraries** own reusable public APIs. libinfinicore supplies provider-neutral resource contracts and Android local/SAF support; libinfinistore owns storage backends; libinfinivault owns archive/filesystem-image handling; libinfiniselect owns file selection and resource-resolution client APIs; libinfinistream owns stream/resource/processor contracts. Format, metadata, media, and shared UI responsibilities are assigned in the component inventory above.",
        "- Apps must consume reusable functionality through the library's public API. They must not import another app's classes, database, private files, build output, or Gradle project. Each app must build from its own checkout and declared/pinned libraries.",
        "- Cross-app operations use documented Android contracts: SAF/DocumentsProvider, Android intents, content URIs, and URI permission grants. Missing companion apps and denied permissions require a local/SAF or explicit error path.",
        "",
        "### Authoritative resource identity and current access",
        "",
        "A resource's authoritative URI/reference records its persistent identity and location. It can identify a local/SAF item, remote object, archive member, or filesystem-image resource. A resolved content URI is the current Android access handle, often accompanied by a time-limited grant. Keep these values distinct: persist the authoritative reference when supplied, pass access URIs only with valid grants, and do not treat a temporary relay as a durable identity. Relative references are resolved against their authoritative parent through libinfiniselect's existing APIs; apps must not independently parse private backend URI formats.",
        "",
        "Infinifolder's DocumentsProvider exposes opaque document IDs through Android SAF. Its libinfiniselect relay currently expires after 24 hours. Android SAF document URIs can themselves be both identity and access URI when the provider defines them as canonical; preserve only grants Android actually issued. Infinikey's DocumentsProvider serves Infinikey-owned data and is separate from Infinifolder storage.",
        "",
        "## Implemented interoperability contracts",
        "",
        "The protocol versions below describe the current codebase. `null` means no InfiniForge protocol version field or negotiation mechanism was found; library version equality is not a substitute for protocol compatibility.",
        "",
    ]
    for p in data["protocols"]:
        implementers = ", ".join(f"[{cid}]({by_id[cid]['repository']})" for cid in p.get("implemented_by", []))
        version = f"`{p['version']}`" if p.get("version") is not None else f"`null` ({p['version_status']})"
        lines += [
            f"### {p['name']}",
            "",
            f"**ID:** `{p['id']}` · **Protocol version:** {version} · **Implemented by:** {implementers}",
            "",
            f"- **Resource identity:** {p['resource_identity']}",
            f"- **Request:** {p['request']}",
            f"- **Response:** {p['response']}",
            f"- **Errors:** {p['errors']}",
            f"- **Compatibility:** {p['compatibility']}",
            f"- **Fallback:** {p['fallback']}",
            f"- **Negotiation:** {p['negotiation']}",
            "",
        ]
    policy = data["versioning_policy"]
    lines += [
        "## Independent component releases and compatibility",
        "",
        f"{policy['scheme']} Each repository releases on its own schedule.",
        "",
        f"- **MAJOR:** {policy['meaning']['major']}",
        f"- **MINOR:** {policy['meaning']['minor']}",
        f"- **PATCH:** {policy['meaning']['patch']}",
        f"- **Tags:** {policy['tag_convention']}",
        f"- **Release notes:** {policy['release_record']}",
        f"- **Version evidence:** {policy['version_sources']}",
        f"- **Dependency pins:** {policy['dependency_versions']}",
        f"- **Protocol compatibility:** {policy['protocol_versions']}",
        "",
        "## Finding and changing an API",
        "",
        "Start at the component's repository README and API/architecture links in the inventory. Read that component's `AGENTS.md` and `docs/README.md` before editing. Before adding shared behavior, inspect the owning library repository; update that library's public API documentation and dependent application docs when behavior changes. For cross-repository changes, check both the source dependency pin and the implemented protocol contract, and preserve optional-app and permission fallback paths.",
        "",
    ]
    return "\n".join(lines)

def check_markdown_links(repo_root: Path) -> list[str]:
    root = repo_root.resolve()
    errors: list[str] = []
    excluded = {".git", ".gradle", "build", "node_modules", ".idea"}
    gitlinks: list[Path] = []
    try:
        indexed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--stage", "-z"],
            capture_output=True, check=False,
        ).stdout
        for item in indexed.split(b"\0"):
            if not item:
                continue
            metadata, path = item.split(b"\t", 1)
            if metadata.startswith(b"160000 "):
                gitlinks.append(Path(path.decode("utf-8", errors="replace")))
    except OSError:
        pass
    for md in root.rglob("*.md"):
        if excluded.intersection(md.relative_to(root).parts):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"{md}: cannot read: {exc}")
            continue
        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip("<>")
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme or target.startswith("//"):
                continue
            local = urllib.parse.unquote(parsed.path)
            if not local:
                continue
            candidate = (root / local.lstrip("/")) if local.startswith("/") else (md.parent / local)
            candidate = candidate.resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"{md.relative_to(root)}: link escapes repository: {target}")
                continue
            if not candidate.exists():
                relative_target = candidate.relative_to(root)
                deferred_to_submodule = any(
                    relative_target == link or link in relative_target.parents
                    for link in gitlinks
                    if not (root / link / ".git").exists()
                )
                if not deferred_to_submodule:
                    errors.append(f"{md.relative_to(root)}: missing link target: {target}")
    return errors


def validate_checkout(data: dict, component_id: str, repo_root: Path, check_links: bool) -> list[str]:
    components = {c["id"]: c for c in data["components"]}
    if component_id not in components:
        return [f"unknown component {component_id}"]
    c = components[component_id]
    root = repo_root.resolve()
    errors: list[str] = []
    for required in ("README.md", "AGENTS.md", "docs/README.md"):
        if not (root / required).is_file():
            errors.append(f"{component_id}: missing {required}")
    for doc in c.get("api_docs", []):
        if not (root / doc).is_file():
            errors.append(f"{component_id}: missing API/architecture documentation {doc}")
    source = c.get("declared_version_source")
    declared = c.get("declared_version")
    if source and declared:
        version_file = root / source
        if not version_file.is_file():
            errors.append(f"{component_id}: missing version source {source}")
        else:
            body = version_file.read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r'\bversionName\s*=\s*["\']([^"\']+)["\']', body)
            if not matches:
                matches = re.findall(r'\bversion\s*=\s*["\']([^"\']+)["\']', body)
            if declared not in matches:
                errors.append(f"{component_id}: declared version {declared} not found in {source}")
    dep_source = c.get("dependency_source")
    if dep_source:
        lock_path = root / dep_source
        if not lock_path.is_file():
            errors.append(f"{component_id}: missing dependency source {dep_source}")
        else:
            try:
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                locked = lock.get("repositories", {})
                expected = set(c.get("dependencies", []))
                actual = set(locked)
                if actual != expected:
                    errors.append(f"{component_id}: manifest dependency IDs differ from {dep_source}; missing={sorted(actual-expected)}, extra={sorted(expected-actual)}")
                for name, entry in locked.items():
                    if name not in components:
                        errors.append(f"{component_id}: lock contains unknown component {name}")
                    if not re.fullmatch(r"[0-9a-f]{40}", str(entry.get("commit", ""))):
                        errors.append(f"{component_id}: invalid pinned commit for {name} in {dep_source}")
                    if entry.get("url") != components.get(name, {}).get("repository", "") + ".git":
                        errors.append(f"{component_id}: repository URL mismatch for {name} in {dep_source}")
            except (OSError, json.JSONDecodeError, AttributeError) as exc:
                errors.append(f"{component_id}: invalid dependency lock {dep_source}: {exc}")
    if check_links:
        errors.extend(check_markdown_links(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate manifest graph, versions, and protocol references")
    render_parser = sub.add_parser("render", help="write the generated ecosystem document")
    render_parser.add_argument("--output", type=Path, required=True)
    check_parser = sub.add_parser("check", help="fail if a generated document differs from the manifest")
    check_parser.add_argument("--file", type=Path, required=True)
    repo_parser = sub.add_parser("validate-repo", help="validate one checked-out component against the manifest")
    repo_parser.add_argument("--component", required=True)
    repo_parser.add_argument("--root", type=Path, required=True)
    repo_parser.add_argument("--links", action="store_true", help="check local relative links in Markdown files")
    repo_parser.add_argument("--generated", action="store_true", help="require docs/ECOSYSTEM.md to match")
    links_parser = sub.add_parser("check-links", help="check local Markdown link targets")
    links_parser.add_argument("--root", type=Path, required=True)
    list_parser = sub.add_parser("list", help="print component IDs for automation")
    list_parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    data = load_manifest()
    errors = validate_manifest(data)
    if errors:
        print("Manifest validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    if args.command == "validate":
        print(f"Manifest valid: {len(data['components'])} components, {len(data['protocols'])} protocols")
        return 0
    if args.command == "render":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(data), encoding="utf-8")
        return 0
    if args.command == "check":
        expected = render(data)
        try:
            actual = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Cannot read generated doc {args.file}: {exc}", file=sys.stderr)
            return 1
        if actual != expected:
            print(f"Stale generated ecosystem document: {args.file}", file=sys.stderr)
            return 1
        print(f"Generated ecosystem document is current: {args.file}")
        return 0
    if args.command == "validate-repo":
        errors = validate_checkout(data, args.component, args.root, args.links)
        if args.generated:
            expected = render(data)
            path = args.root / "docs/ECOSYSTEM.md"
            try:
                actual = path.read_text(encoding="utf-8")
            except OSError:
                actual = None
            if actual != expected:
                errors.append(f"{args.component}: docs/ECOSYSTEM.md is missing or stale")
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Repository validation passed: {args.component}")
        return 0
    if args.command == "check-links":
        errors = check_markdown_links(args.root)
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Markdown link targets are valid under {args.root}")
        return 0
    if args.command == "list":
        ids = [c["id"] for c in data["components"]]
        print(json.dumps(ids) if args.json else "\n".join(ids))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
