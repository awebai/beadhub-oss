#!/usr/bin/env python3
"""Cheap source contract for the canonical public site."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_VERSION = "2026-08-25-awebai-transition"


def _count_casefold(path: Path, needle: str) -> int:
    return path.read_text().casefold().count(needle.casefold())


def main() -> None:
    base = (ROOT / "layouts/_default/baseof.html").read_text()
    home = (ROOT / "content/_index.md").read_text()
    getting_started = (ROOT / "content/docs/getting-started.md").read_text()
    analytics = (ROOT / "static/js/activation-analytics.js").read_text()
    provenance = (ROOT / "PROVENANCE.md").read_text()
    terms_path = ROOT / "content/terms.md"
    privacy_path = ROOT / "content/privacy.md"
    terms = terms_path.read_text()
    privacy = privacy_path.read_text()
    history = (ROOT / "content/legal-history.md").read_text()
    agent_index = (ROOT / "static/llms.txt").read_text()
    activation_surfaces = "\n".join((base, home, getting_started))

    assert "HUGO_PLAUSIBLE_SCRIPT_URL" in base
    assert "/js/activation-analytics.js" in base
    assert "BeadHub Activation" in analytics
    assert "step: 'visit'" in analytics
    assert "surface: 'site'" in analytics
    for forbidden in ("api_key", "email", "message", "task_id", "repo"):
        assert forbidden not in analytics
    for required in (
        "https://github.com/awebai/beadhub-oss",
        "https://github.com/awebai/bdh",
        "https://raw.githubusercontent.com/awebai/bdh/main/install.sh",
        "BEADHUB_URL=https://app.beadhub.ai/api",
        "Generate setup command",
    ):
        assert required in activation_surfaces
    for forbidden in (
        'href="https://github.com/beadhub/',
        "https://raw.githubusercontent.com/beadhub/",
        'href="https://github.com/juanre/',
        "https://raw.githubusercontent.com/juanre/",
    ):
        assert forbidden not in activation_surfaces
    for forbidden in (
        "register?tier=pro",
        "register?tier=business",
    ):
        assert forbidden not in home
    assert home.count("Paid signup is temporarily paused") == 2
    assert "7b1f291539c0230106db2a339372a85d9c410896" in provenance

    for policy in (terms, privacy):
        assert POLICY_VERSION in policy
        assert "2026-09-01" in policy
        assert "2026-10-02" in policy
        assert "Awebai, Inc." in policy
        assert "beadhub@beadhub.ai" in policy
    assert "Operated by Awebai, Inc. beginning October 2, 2026" in base
    assert "&copy;" not in base
    assert "1a2b1e8351367afcddb837a1c438e129a7990b9e" in history
    assert "https://beadhub.ai/terms/" in agent_index
    assert "https://beadhub.ai/privacy/" in agent_index
    assert "https://beadhub.ai/legal-history/" in agent_index

    # The previous operator may appear only in the explicit transition clauses.
    allowed_legacy_counts = {terms_path: 2, privacy_path: 1}
    for path in ROOT.rglob("*"):
        if not path.is_file() or "public" in path.parts:
            continue
        if path.suffix not in {
            ".md",
            ".html",
            ".txt",
            ".toml",
            ".json",
            ".js",
            ".yaml",
            ".yml",
        }:
            continue
        expected = allowed_legacy_counts.get(path, 0)
        assert _count_casefold(path, "Thestarmaps") == expected, path
        for legacy_marker in (
            "irish company",
            "irish data protection",
            "laws of ireland",
            "courts of ireland",
            "data protection commission",
            "dataprotection.ie",
            "fitzwilliam square",
            "ireland",
            "dublin 2",
            "d02 rd28",
        ):
            assert _count_casefold(path, legacy_marker) == 0, (path, legacy_marker)

    public = ROOT / "public"
    if public.exists():
        public_terms = public / "terms/index.html"
        public_privacy = public / "privacy/index.html"
        public_history = public / "legal-history/index.html"
        for path in (public_terms, public_privacy, public_history):
            assert path.is_file(), path
        assert _count_casefold(public_terms, "Thestarmaps") == 2
        assert _count_casefold(public_privacy, "Thestarmaps") == 1
        assert _count_casefold(public_history, "Thestarmaps") == 0
        public_feed = public / "index.xml"
        assert _count_casefold(public_feed, "Thestarmaps") == 2
        for path in public.rglob("*"):
            if not path.is_file() or path.suffix not in {
                ".html",
                ".xml",
                ".txt",
                ".js",
                ".json",
                ".yaml",
                ".yml",
            }:
                continue
            if path in {public_terms, public_privacy, public_feed}:
                continue
            assert _count_casefold(path, "Thestarmaps") == 0, path
            for legacy_marker in (
                "irish company",
                "irish data protection",
                "laws of ireland",
                "courts of ireland",
                "data protection commission",
                "dataprotection.ie",
                "fitzwilliam square",
                "ireland",
                "dublin 2",
                "d02 rd28",
            ):
                assert _count_casefold(path, legacy_marker) == 0, (path, legacy_marker)

    print("site contract: ok")


if __name__ == "__main__":
    main()
