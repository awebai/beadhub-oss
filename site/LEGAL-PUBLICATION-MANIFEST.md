# BeadHub legal/public identity publication manifest

Status: staged; do not publish before authorized advance notice

Policy version: `2026-08-25-awebai-transition`

Advance-notice date: 2026-09-01

Effective-date cutover: no earlier than 2026-10-02

## Canonical source and generated pages

| Surface | Canonical source | Generated/public target | Cutover behavior |
| --- | --- | --- | --- |
| Terms | `site/content/terms.md` | `/terms/index.html` and `https://beadhub.ai/terms/` | Publish for advance notice on 2026-09-01; old terms remain effective through 2026-10-01 |
| Privacy Notice | `site/content/privacy.md` | `/privacy/index.html` and `https://beadhub.ai/privacy/` | Publish for advance notice on 2026-09-01; old policy remains effective through 2026-10-01 |
| Legal history | `site/content/legal-history.md` | `/legal-history/index.html` and `https://beadhub.ai/legal-history/` | Publish with advance notice; links pin the prior canonical source commit |
| Global footer | `site/layouts/_default/baseof.html` | every generated HTML page | Explicitly says the Awebai date is future-effective rather than current before cutover |
| Agent-readable index | `site/static/llms.txt` | `/llms.txt` | Canonical Terms, Privacy, and legal-history links are explicit and verified in generated output |

`site/scripts/test_site_contract.py` scans both canonical source and fresh generated
output. It permits the prior company name only in the three exact transition
clauses in the current Terms/Privacy pages and fails on shortened old-company
references, legacy Irish jurisdiction/regulator/address language, or any other
stale public use covered by the known inventory.

## Deployment mirror

The deployment mirror is `beadhub.ai` in the BeadHub coordination workspace. It is
not an authoring source. At publication time, copy the exact reviewed canonical
`site/` tree into that mirror, build it once, verify the generated pages and source
commit, then push the deploy branch. Do not hand-edit the mirror or publish this
staged canonical commit before the approved 2026-09-01 notice action.

## Hosted application and notices

The hosted application must link to the canonical URLs above from registration,
OAuth, invitation, billing, dashboard, and account surfaces. The policy-acceptance
schema and notice email are owned by the separate SaaS implementation tasks. The
advance-notice publication/send and the no-earlier-than-2026-10-02 effective-date
Stripe/Render cutover are distinct operations.

## Package and metadata audit

- The Python package already points Homepage, Documentation, Repository, and Issues
  at `awebai/beadhub-oss` and makes no company/operator assertion.
- The dashboard package has intentionally preserved the compatibility name
  `@beadhub/dashboard`; it contains no stale company, address, jurisdiction,
  contact, policy, or repository assertion.
- No existing PyPI/npm artifact is rewritten. If the next immutable package adds
  policy/company metadata, it must use the effective version and canonical URLs
  from this manifest; no package publication is required merely to remove a stale
  assertion because none was found.

## Historical exemptions

The prior policies remain immutable at canonical commit
`1a2b1e8351367afcddb837a1c438e129a7990b9e`. Their historical company and
jurisdiction language is evidence of what applied before the transition and must not be changed.
The site contract scans the current source/build, not immutable Git history.
