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

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: Licenses the project policy accepts for the distributed voice tree.
#: An alias table by design: the same accepted license in its attested
#: spellings (SPDX, setuptools-era long forms). Nothing copyleft is
#: admitted here; the forbidden-marker check runs before this set.
PERMISSIVE_LICENSES = {
    "apache-2.0", "apache 2.0", "apache license 2.0", "apache software license",
    "apache 2.0 license",
    "mit", "mit license", "bsd", "bsd-2-clause", "bsd-3-clause",
    "bsd license", "bsd 3-clause license", "3-clause bsd license",
    "isc", "python software foundation license", "psf",
    "zlib", "unlicense", "cc0-1.0", "public domain", "cnri-python",
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
    """'permissive' | 'forbidden' | 'unknown' for one license string.

    SPDX structure is honored conservatively: a compound joined by
    AND is permissive only when EVERY component is; a "WITH
    <exception>" suffix is stripped before judging the base license
    (SPDX exceptions only ever grant additional rights); an OR
    compound stays 'unknown' — a choice of licenses is a human-review
    question, not an automatic pass.
    """
    text = (raw or "").strip().lower()
    if not text:
        return "unknown"
    if any(marker in text for marker in FORBIDDEN_MARKERS):
        return "forbidden"
    parts: list[str] = []
    for comma_part in text.replace(";", ",").split(","):
        for and_part in comma_part.split(" and "):
            part = and_part.strip()
            if " with " in part:
                part = part.split(" with ", 1)[0].strip()
            if part:
                parts.append(part)
    if parts and all(part in PERMISSIVE_LICENSES for part in parts):
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

    @property
    def checked(self) -> int:
        """How many distributions the audit judged (UI display)."""
        return len(self.findings)

    @property
    def violations(self) -> list[str]:
        """Human-readable failure lines (UI display; install.backend_status)."""
        out: list[str] = []
        for finding in self.failures:
            line = (f"{finding.distribution} "
                    f"({finding.license or 'no license metadata'}): {finding.verdict}")
            if finding.reason:
                line += f" — {finding.reason}"
            out.append(line)
        return out

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


def _declared_license(metadata) -> str:
    """Extract a distribution's declared license EXPRESSION.

    Modern packaging (PEP 639) puts the SPDX expression in
    ``License-Expression``; older packages put a short expression in
    ``License`` — or the field's FULL TEXT, which is not an expression
    and must never reach the classifier (a PSF license body containing
    the word "GPL" in a comment would otherwise read as forbidden,
    and an MIT body as unknown). Fallback order: License-Expression →
    short License field → OSI classifier.
    """
    expr = (metadata.get("License-Expression") or "").strip()
    if expr:
        return expr
    raw = (metadata.get("License") or "").strip()
    if raw and raw != "UNKNOWN":
        if "\n" not in raw and len(raw) <= 80:
            return raw
        # Multi-line field: some wheels head the license body with the
        # short expression ("MIT License\n\nCopyright ..."). Trust a
        # first line only when it is shaped like an expression (short,
        # few words, license-shaped) — a prose heading ("License
        # agreement for ...") or a copyright line is not one and falls
        # through to the classifiers.
        first = raw.splitlines()[0].strip()
        words = first.split()
        if (len(first) <= 40 and len(words) <= 4
                and ("license" in first.lower() or len(words) == 1)):
            return first
    classifiers = [c for c in (metadata.get_all("Classifier") or [])
                   if c.startswith("License :: OSI Approved ::")]
    if classifiers:
        return classifiers[0].split("::")[-1].strip()
    return ""


#: Human-reviewed declarations for wheels whose metadata declares NO
#: license at all (the audit's 'unknown — human review required'
#: verdict, answered and recorded). Consulted ONLY when a wheel
#: declares nothing; every entry cites its evidence, and the same
#: record lives in docs/VOICE_LICENSE_MATRIX.md. A distribution not
#: listed here and declaring nothing stays unknown — and fails.
REVIEWED_DECLARATIONS: dict[str, str] = {
    # Wheel header is silent, but the wheel bundles the Apache
    # License 2.0 text itself (dist-info/licenses/LICENSE), and the
    # upstream project (wenet-e2e/WeTextProcessing) is Apache-2.0.
    # Evidence read on purplelongship, 2026-10-13.
    "wetextprocessing": "Apache-2.0",
}


def installed_distributions() -> dict[str, str]:
    """Collect {name: license expression} for every installed distribution."""
    from importlib.metadata import distributions

    out: dict[str, str] = {}
    for dist in distributions():
        name = dist.metadata.get("Name") or ""
        if not name:
            continue
        declared = _declared_license(dist.metadata)
        if not declared:
            declared = REVIEWED_DECLARATIONS.get(_normalize(name), "")
        out[name] = declared
    return out


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
