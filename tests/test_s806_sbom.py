"""S806 (roadmap): SBOM + license manifest + release license gate.

The gate reuses the S504 classifier over the distribution set: an
injected copyleft distribution fails the gate and appears in the
manifest with its verdict; a clean permissive set passes. Artifacts
are schema-shaped and deterministic.
"""

from __future__ import annotations

import json

from runmal.__main__ import main as runmal_main
from runmal.release.sbom import (
    DistributionRecord,
    build_license_manifest,
    build_sbom,
    collect_distributions,
    gate_report,
)

CLEAN = [
    DistributionRecord("fastapi", "0.115.0", "MIT"),
    DistributionRecord("sqlalchemy", "2.0.0", "MIT"),
    DistributionRecord("sqlite-vec", "0.1.9", "Apache-2.0"),
    DistributionRecord("httpx", "0.27.0", "BSD-3-Clause"),
]


def test_sbom_shape_and_determinism():
    sbom = build_sbom(CLEAN)
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["component"]["name"] == "runmal"
    names = [c["name"] for c in sbom["components"]]
    assert names == sorted(names, key=str.lower)
    fastapi = next(c for c in sbom["components"] if c["name"] == "fastapi")
    assert fastapi["purl"] == "pkg:pypi/fastapi@0.115.0"
    assert fastapi["licenses"] == [{"expression": "MIT"}]
    assert build_sbom(CLEAN) == sbom  # deterministic
    json.dumps(sbom)  # JSON-serializable


def test_gate_passes_clean_and_fails_copyleft():
    assert gate_report(CLEAN).passed
    dirty = CLEAN + [DistributionRecord("phonemizer-fork", "1.0", "MIT")]
    report = gate_report(dirty)
    assert not report.passed  # forbidden distribution name beats its claim
    gpl = CLEAN + [DistributionRecord("some-lib", "1.0", "GPL-3.0-only")]
    assert not gate_report(gpl).passed
    unknown = CLEAN + [DistributionRecord("mystery", "1.0", "LicenseRef-Proprietary")]
    assert not gate_report(unknown).passed  # unknown requires human review


def test_license_manifest_records_verdicts():
    dirty = CLEAN + [DistributionRecord("some-lib", "1.0", "GPL-3.0-only")]
    manifest = build_license_manifest(dirty)
    assert manifest["gate_passed"] is False
    assert manifest["summary"] == {
        "total": 5,
        "permissive": 4,
        "forbidden": 1,
        "unknown": 0,
    }
    bad = next(d for d in manifest["distributions"] if d["name"] == "some-lib")
    assert bad["verdict"] == "forbidden"
    assert build_license_manifest(CLEAN)["gate_passed"] is True


def test_real_installed_set_collects_and_classifies():
    records = collect_distributions()
    names = {r.name.lower() for r in records}
    assert "fastapi" in names and "sqlalchemy" in names
    assert all(r.version for r in records)
    manifest = build_license_manifest(records)
    json.dumps(manifest)
    assert manifest["summary"]["total"] == len(records)


def test_release_cli(tmp_path, capsys):
    out = tmp_path / "sbom.json"
    assert runmal_main(["release", "sbom", "--out", str(out)]) == 0
    capsys.readouterr()  # drain the "wrote ..." line before the JSON call
    data = json.loads(out.read_text())
    assert data["bomFormat"] == "CycloneDX"
    assert runmal_main(["release", "licenses"]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert "distributions" in manifest
