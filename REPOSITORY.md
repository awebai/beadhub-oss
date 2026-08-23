# Repository authority and history

`awebai/beadhub-oss` is the canonical public source repository for BeadHub.
It owns the BeadHub-specific open-source composition: the beads-facing server
adapter, dashboard, self-host packaging, and public federation documentation.

BeadHub is an aweb deployment with a beads-shaped surface. It consumes the
modern public aweb implementation from `awebai/aweb`; it must not grow a
private or independently evolving fork of aweb identity, mail, chat, wake, or
presence. Gaps in those primitives belong upstream in aweb.

The public Go client remains at `beadhub/bdh` for module and installer
compatibility. Its current URL is a public API: existing `go install` commands,
release downloads, and user automation must continue to work while its scope
is reduced to claims, presence, wake, mail/chat, escalation, and delegation to
the beads data plane.

## Recovery provenance

This repository was recovered on 2026-08-23 from the surviving
`awebai/aweb` branch `beadhub-legacy`. The imported main branch began at
commit `0a13a1f6dd334768732f7c8c40593c343a80035a`, also preserved by the
`beadhub-final` tag. The `legacy-source` remote is retained read-only as
provenance; new work lands only in `origin` (`awebai/beadhub-oss`).

## Repository boundaries

- `awebai/beadhub-oss` is authoritative for OSS BeadHub code and public docs.
- `awebai/beadhub-saas` is authoritative for the private hosted overlay and
  production release definition.
- `beadhub/bdh` remains the compatibility release repository for the Go CLI.
- `beadhub/beadhub-cloud` remains the compatibility image-publishing mirror
  during the revival release. It is not a second development authority.
- The current product strategy lives outside the runtime repositories in the
  awebai strategy library.

Do not transfer, rename, archive, or force-push a compatibility repository as
part of ordinary feature work. A controlled release migration must first prove
the replacement URL, package, and rollback path.
