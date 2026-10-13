"""Voice dependency license gate (S504, policy: docs/VOICE_LICENSE_MATRIX.md).

Rúnmál's distributed voice stack is PERMISSIVE-ONLY (Apache-2.0 / MIT /
BSD / ISC / MPL-2.0 file-level copyleft excluded from the shipped runtime
tree by policy decision — see the matrix). A permissive top-level package
does NOT clear its tree: this module audits the *actual installed
distributions* that a TTS path would ship, and refuses paths whose tree
contains a forbidden or unreviewed license.

The known trap (matrix §"eSpeak/eSpeak-NG paths"): Kokoro wrappers route
phonemization through eSpeak-NG (GPL-3.0) via ``espeakng-loader`` /
``phonemizer(-fork)``. GPL-3.0 in the distributed runtime tree fails this
policy, so any path requiring those distributions is REJECTED here, in
code, before synthesis is possible — licensing direction is not routed
around (ROADMAP S504 hard gate).

The audit is a pure function over a {distribution: license} map so it is
unit-testable without the heavy environment; :func:`installed_distributions`
collects the real map from importlib.metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Licenses the project policy accepts for the distributed voice tree.
PERMISSIVE_LICENSES = {
    "apache-2.0", "apache 2.0", "apache license 2.0", "apache software license",
    "mit", "mit license", "bsd", "bsd-2-clause", "bsd-3-clause",
    "bsd license", "isc", "python software foundation license", "psf",
    "zlib", "unlicense", "cc0-1.0",
}

#: License markers that fail the gate outright.
FORBIDDEN_MARKERS = ("gpl", "agpl", "lgpl", "copyleft", "noncommercial",
                     "non-commercial", "cc-by-nc")

#: Distributions that must never appear in the shipped voice tree,
#: regardless of what a metadata license field claims (they exist to
#: load eSpeak-NG, GPL-3.0).
FORBIDDEN_DISTRIBUTIONS = {
    "espeakng-loader", "espeak-ng", "espeakng", "phonemizer",
    "phonemizer-fork", "piper-phonemize", "py-espeak-ng",
}


def _normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def classify_license(raw: str) -> str:
    """'permissive' | 'forbidden' | 'unknown' for one license string."""
    text = (raw or "").strip().lower()
    if not text:
        return "unknown"
    if any(marker in text for marker in FORBIDDEN_MARKERS):
        return "forbidden"
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    if all(part in PERMISSIVE_LICENSES for part in parts if part):
        return "permissive"
    return "unknown"


@dataclass
class AuditFinding:
    distribution: str
    license: str
    verdict: str  # permissive | forbidden | unknown
    reason: str = ""


@dataclass
class AuditReport:
    findings: list[AuditFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.findings) and all(f.verdict == "permissive" for f in self.findings)

    @property
    def failures(self) -> list[AuditFinding]:
        return [f for f in self.findings if f.verdict != "permissive"]

    def summary(self) -> str:
        lines = [f"{'PASS' if self.passed else 'FAIL'}: voice license audit "
                 f"({len(self.findings)} distributions)"]
        for finding in self.failures:
            lines.append(f"  {finding.verdict}: {finding.distribution} "
                         f"({finding.license}) {finding.reason}")
        return "\n".join(lines)


def audit_snapshot(snapshot: Mapping[str, str]) -> AuditReport:
    """Audit one backend's installed tree (name -> license string).

    This is the per-backend admission entry point (ADR-0005): the same
    pure classifier as :func:`audit_distributions`, named for its role —
    a *snapshot* of one backend's real installed tree.
    """
    return audit_distributions(dict(snapshot))


def audit_distributions(distributions: dict[str, str]) -> AuditReport:
    """Audit a {distribution name: license string} map against policy."""
    report = AuditReport()
    for name in sorted(distributions, key=_normalize):
        key = _normalize(name)
        raw_license = distributions[name]
        if key in FORBIDDEN_DISTRIBUTIONS:
            report.findings.append(AuditFinding(
                name, raw_license, "forbidden",
                "distribution is an eSpeak-NG carrier (GPL-3.0) — rejected by policy"))
            continue
        verdict = classify_license(raw_license)
        reason = "" if verdict == "permissive" else (
            "license is copyleft/restricted" if verdict == "forbidden"
            else "license not in the reviewed permissive set — human review required")
        report.findings.append(AuditFinding(name, raw_license, verdict, reason))
    return report


def installed_distributions() -> dict[str, str]:
    """Collect {name: license} for every installed distribution."""
    from importlib.metadata import distributions

    out: dict[str, str] = {}
    for dist in distributions():
        name = dist.metadata.get("Name") or ""
        if not name:
            continue
        license_text = dist.metadata.get("License") or ""
        if not license_text or license_text == "UNKNOWN":
            classifiers = [c for c in (dist.metadata.get_all("Classifier") or [])
                           if c.startswith("License :: OSI Approved ::")]
            license_text = classifiers[0].split("::")[-1].strip() if classifiers else ""
        out[name] = license_text
    return out


#: The exact runtime tree the shipped Kokoro ONNX path (S504) is audited
#: against — pinned expectations, reviewed 2026-10-12 (see the filled
#: evidence table in docs/VOICE_LICENSE_MATRIX.md). Assets (model/voices)
#: are audited separately there: Kokoro-82M weights + voices, Apache-2.0.
def installed_distributions() -> dict[str, str]:
    """Collect {name: license} for every installed distribution."""
    from importlib.metadata import distributions

    out: dict[str, str] = {}
    for dist in distributions():
        name = dist.metadata.get("Name") or ""
        if not name:
            continue
        license_text = dist.metadata.get("License") or ""
        if not license_text or license_text == "UNKNOWN":
            classifiers = [c for c in (dist.metadata.get_all("Classifier") or [])
                           if c.startswith("License :: OSI Approved ::")]
            license_text = classifiers[0].split("::")[-1].strip() if classifiers else ""
        out[name] = license_text
    return out


#: The exact runtime tree the shipped Kokoro ONNX path (S504) is audited
#: against — pinned expectations, reviewed 2026-10-12 (see the filled
#: evidence table in docs/VOICE_LICENSE_MATRIX.md). Assets (model/voices)
#: are audited separately there: Kokoro-82M weights + voices, Apache-2.0.
VOICE_RUNTIME_TREE = (
    "onnxruntime",  # MIT — inference runtime for the ONNX graph
    "numpy",  # BSD-3-Clause — audio tensors
    "misaki",  # Apache-2.0 — G2P (used WITHOUT its espeak fallback)
    "kokoro-onnx-model",  # pseudo-entry: ONNX graph derived from Kokoro-82M (Apache-2.0)
)


def audit_voice_environment() -> AuditReport:
    """Audit the live environment's voice-relevant distributions.

    Only distributions that are part of the voice runtime tree (plus any
    forbidden carriers, wherever they hide) are judged — unrelated site
    packages are out of scope for the S504 gate.
    """
    installed = installed_distributions()
    relevant: dict[str, str] = {}
    for name, license_text in installed.items():
        key = _normalize(name)
        if key in FORBIDDEN_DISTRIBUTIONS or key in {
                _normalize(n) for n in VOICE_RUNTIME_TREE if n != "kokoro-onnx-model"}:
            relevant[name] = license_text
    if not any(_normalize(n) == "onnxruntime" for n in relevant):
        relevant["onnxruntime"] = ""  # missing -> unknown -> audit fails honestly
    return audit_distributions(relevant)


def installed_snapshot(package_names: Iterable[str] | None = None) -> dict[str, str]:
    """License snapshot of the current environment (optionally filtered).

    With ``package_names=None`` this snapshots every installed
    distribution — the right input for auditing the *default shipped
    tree* (the whole environment Rúnmál runs in). With names given, only
    distributions whose normalized name is in the set are included —
    the right input for auditing one user-installed backend's tree.
    """
    dists = installed_distributions()
    if package_names is None:
        return dists
    wanted = {_normalize(n) for n in package_names}
    return {name: lic for name, lic in dists.items() if _normalize(name) in wanted}
