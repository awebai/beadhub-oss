#!/usr/bin/env python3
"""Cheap source contract for the canonical public site."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    base = (ROOT / "layouts/_default/baseof.html").read_text()
    home = (ROOT / "content/_index.md").read_text()
    getting_started = (ROOT / "content/docs/getting-started.md").read_text()
    analytics = (ROOT / "static/js/activation-analytics.js").read_text()
    provenance = (ROOT / "PROVENANCE.md").read_text()
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

    print("site contract: ok")


if __name__ == "__main__":
    main()
