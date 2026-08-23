#!/usr/bin/env python3
"""Cheap source contract for the canonical public site."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    base = (ROOT / "layouts/_default/baseof.html").read_text()
    analytics = (ROOT / "static/js/activation-analytics.js").read_text()
    provenance = (ROOT / "PROVENANCE.md").read_text()

    assert "HUGO_PLAUSIBLE_SCRIPT_URL" in base
    assert "/js/activation-analytics.js" in base
    assert "BeadHub Activation" in analytics
    assert "step: 'visit'" in analytics
    assert "surface: 'site'" in analytics
    for forbidden in ("api_key", "email", "message", "task_id", "repo"):
        assert forbidden not in analytics
    assert "7b1f291539c0230106db2a339372a85d9c410896" in provenance

    print("site contract: ok")


if __name__ == "__main__":
    main()
