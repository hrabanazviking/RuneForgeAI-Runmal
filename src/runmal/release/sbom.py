"""SBOM + license manifest + release license gate (S806).

Per SECURITY_AND_PRIVACY / the S504 policy: a release ships with a
software bill of materials and a license manifest generated from the
REAL installed distribution set, and the same S504 classifier that
guards the voice tree gates the whole shipped tree — a distribution
whose license is copyleft/restricted, or that human review has not
cleared, fails the release gate. Nothing here invents metadata: names,
versions, and license expressions come from the installed environment
(``importlib.metadata``), classified by ``voice.license_audit``.

Artifacts:
- SBOM: CycloneDX 1.5-shaped JSON (components with purl + licenses).
- License manifest: per-distribution verdicts + gate summary.
Both are deterministic (sorted, fixed key order content) so a release
diff shows exactly what changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata as importlib_metadata

from runmal import __version__
from runmal.voice.license_audit import audit_distributions, installed_distributions


@dataclass(frozen=True)
class DistributionRecord:
    name: str
    version: str
    license: str


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def collect_distributions(
    records: list[DistributionRecord] | None = None,
) -> list[DistributionRecord]:
    """The installed distribution set (or an injected one, for tests)."""
    if records is not None:
        return sorted(records, key=lambda r: _normalize(r.name))
    licenses = installed_distributions()
    by_key = {_normalize(name): expr for name, expr in licenses.items()}
    out: list[DistributionRecord] = []
    seen: set[str] = set()
    for dist in importlib_metadata.distributions():
        name = dist.metadata.get("Name") or ""
        if not name or _normalize(name) in seen:
            continue
        seen.add(_normalize(name))
        out.append(
            DistributionRecord(
                name=name,
                version=dist.version or "",
                license=by_key.get(_normalize(name), ""),
            )
        )
    return sorted(out, key=lambda r: _normalize(r.name))


def build_sbom(records: list[DistributionRecord] | None = None) -> dict:
    """CycloneDX 1.5-shaped SBOM for the distribution set."""
    dists = collect_distributions(records)
    components = []
    for record in dists:
        component = {
            "type": "library",
            "name": record.name,
            "version": record.version,
            "purl": f"pkg:pypi/{_normalize(record.name)}@{record.version}",
        }
        if record.license:
            component["licenses"] = [{"expression": record.license}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "runmal",
                "version": __version__,
            }
        },
        "components": components,
    }


def gate_report(records: list[DistributionRecord] | None = None):
    """The S504 audit over the distribution set (release gate input)."""
    dists = collect_distributions(records)
    return audit_distributions({r.name: r.license for r in dists})


def build_license_manifest(records: list[DistributionRecord] | None = None) -> dict:
    """License manifest: every distribution, its license, its verdict."""
    dists = collect_distributions(records)
    report = audit_distributions({r.name: r.license for r in dists})
    verdicts = {f.distribution: f for f in report.findings}
    entries = []
    for record in dists:
        finding = verdicts.get(record.name)
        entries.append(
            {
                "name": record.name,
                "version": record.version,
                "license": record.license,
                "verdict": finding.verdict if finding else "unknown",
                "reason": finding.reason if finding else "",
            }
        )
    return {
        "app": "runmal",
        "app_version": __version__,
        "policy": "permissive-only shipped tree (S504); unknown requires review",
        "gate_passed": report.passed,
        "summary": {
            "total": len(entries),
            "permissive": sum(1 for e in entries if e["verdict"] == "permissive"),
            "forbidden": sum(1 for e in entries if e["verdict"] == "forbidden"),
            "unknown": sum(1 for e in entries if e["verdict"] == "unknown"),
        },
        "distributions": entries,
    }
