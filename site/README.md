# BeadHub public site

This directory is the canonical source for `beadhub.ai`. Build it with the
checked Hugo version:

```bash
make check
```

The build fails when Hugo differs from [`.hugo-version`](.hugo-version).
For an urgent local proof only, an operator may set
`ALLOW_HUGO_VERSION_MISMATCH=1`; the resulting version mismatch and accepted
risk must be recorded with the artifact.

## Analytics configuration

BeadHub uses the same privacy-conscious provider and event contract as aweb:
Plausible, with no cookies and no analytics secret in this repository. Copy the
site-specific script URL shown by Plausible for the `beadhub.ai` site and pass
it at build time:

```bash
HUGO_PLAUSIBLE_SCRIPT_URL=https://plausible.io/js/pa-REPLACE.js make build
```

The URL is public configuration, not a credential. Missing URLs and values
outside `https://plausible.io/js/*.js` leave analytics disabled. The site still
builds and works. The shared event is `BeadHub Activation`; this surface emits only
`step=visit` and `surface=site`. Plausible's standard pageview supplies
referrer/campaign attribution without exposing message, task, key, account, or
repository content.

## Deployment mirror

The legacy `juanre/beadhub.ai` repository remains the current deployment
mirror until the human-controlled Render change. Do not develop there. To
prepare a mirror update without relying on GitHub Actions:

1. Build and review this directory in `awebai/beadhub-oss`.
2. Export the reviewed tree with `git archive <reviewed-sha>:site` into a clean
   staging directory.
3. Compare that staging directory with a clean legacy checkout, copy the
   reviewed source delta, and build it with the same Hugo version.
4. Commit the mirror locally and review it. Before any push, Juan or the
   deployment operator must confirm whether Render auto-deploy is enabled. If
   a push could deploy, stop and leave the reviewed commit local until Juan
   explicitly authorizes the production effect. Never assume a mirror push and
   the manual Render flip are separate actions.

The import boundary and exact source commit are recorded in
[`PROVENANCE.md`](PROVENANCE.md).
