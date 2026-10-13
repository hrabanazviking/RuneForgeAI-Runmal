"""S807 (roadmap): release/versioning dry-run consistency check.

The real tree must be consistent (pyproject == package version,
archive format declared, schema HEAD, CHANGELOG entry present), and
every injected desync must be caught by name.
"""

from __future__ import annotations

from pathlib import Path

from runmal import __version__
from runmal.__main__ import main as runmal_main
from runmal.release.versioning import check_release_consistency

ROOT = Path(__file__).resolve().parent.parent


def test_real_tree_is_consistent():
    check = check_release_consistency(root=ROOT)
    assert check.ok, check.summary()
    facts = {f.fact: f for f in check.findings}
    assert facts["app_version"].ok
    assert facts["archive_format_version"].ok
    assert facts["schema_revision"].ok
    assert facts["changelog_entry"].ok


def test_desynced_app_version_is_caught():
    check = check_release_consistency(root=ROOT, pyproject_version="9.9.9")
    assert not check.ok
    bad = [f.fact for f in check.findings if not f.ok]
    assert bad == ["app_version"]
    check = check_release_consistency(root=ROOT, app_version="2.0.0")
    assert not check.ok


def test_missing_changelog_entry_is_caught(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [0.0.1]\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "runmal"\nversion = "0.1.0"\n')
    check = check_release_consistency(root=tmp_path)
    assert not check.ok
    bad = {f.fact for f in check.findings if not f.ok}
    assert "changelog_entry" in bad


def test_schema_and_archive_facts_are_real():
    from runmal.db.migrations import MIGRATIONS
    from runmal.portable.archive import FORMAT_VERSION

    check = check_release_consistency(root=ROOT)
    facts = {f.fact: f.detail for f in check.findings}
    assert MIGRATIONS[-1][0] in facts["schema_revision"]
    assert f"v{FORMAT_VERSION}" in facts["archive_format_version"]
    assert __version__ in str(facts)


def test_release_check_cli(capsys):
    assert runmal_main(["release", "check"]) == 0
    out = capsys.readouterr().out
    assert "release check: OK" in out
