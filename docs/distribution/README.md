# Distribution handoff

This directory contains reviewable inputs for compatibility locations that are
not canonical BeadHub development repositories.

## `github.com/beadhub/beadhub`

As checked on 2026-08-23, GitHub redirects this path to `awebai/aweb`. Restoring
the path would replace that redirect and is therefore an explicit repository
ownership change, not an incidental documentation edit. No transfer, rename,
or repository creation was performed.

When the `beadhub` organization owner approves restoring the path, create a
public compatibility repository at the old URL and use
[`legacy-beadhub-README.md`](legacy-beadhub-README.md) as its README. The repo
should contain no product implementation; it points readers to the canonical
OSS server, compatible CLI, hosted service, beads, and aweb.

## Beads community-tools listing

[`beads-community-tools.patch`](beads-community-tools.patch) is prepared
against `steveyegge/beads` commit
`6331a9771a5a58dcf9c9313970d0db7c8b4756f8`. It adds BeadHub as a coordination
server, links `beadhub.ai`, and describes the current aweb/beads boundary
without presenting the planned federation rebase as already shipped.
Apply it in an up-to-date beads checkout, review upstream changes, then submit
through the beads contribution process. This repository does not push to or
impersonate the unrelated upstream checkout.
