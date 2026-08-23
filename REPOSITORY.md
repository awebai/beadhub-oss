# Repository authority and history

`awebai/beadhub-oss` is the canonical public source repository for BeadHub.
It owns the BeadHub-specific open-source composition: the beads-facing server
adapter, dashboard, self-host packaging, and public federation documentation.

BeadHub's target architecture is an aweb deployment with a beads-shaped
surface. The recovered Phase-0 service uses an older aweb line while it is
rebased onto the modern public implementation from `awebai/aweb`; it must not grow a
private or independently evolving fork of aweb identity, mail, chat, wake, or
presence. Gaps in those primitives belong upstream in aweb.

The public Go client is developed and released from `awebai/bdh` starting with
v0.12.0. The original `beadhub/bdh` history, module path, installer, and release
downloads through v0.11.7 remain available for compatibility. Older installed
clients continue to work; running the canonical installer once moves them to
the new self-update line.

## Recovery provenance

This repository was recovered on 2026-08-23 from the surviving
`awebai/aweb` branch `beadhub-legacy`. The imported main branch began at
commit `0a13a1f6dd334768732f7c8c40593c343a80035a`, also preserved by the
`beadhub-final` tag. The `legacy-source` remote is retained read-only as
provenance; new work lands only in `origin` (`awebai/beadhub-oss`).

The canonical public site now lives in [`site/`](site/). It was recovered from
the deployable source at `juanre/beadhub.ai` commit
`7b1f291539c0230106db2a339372a85d9c410896`; operational state and generated
output from that repository were deliberately excluded. The legacy repository
remains the deployment mirror until its Render service is manually pointed at
an artifact built from this source. See [`site/PROVENANCE.md`](site/PROVENANCE.md)
for the exact boundary and mirror procedure.

## Repository boundaries

- `awebai/beadhub-oss` is authoritative for OSS BeadHub code and public docs.
- `awebai/beadhub-saas` is authoritative for the private hosted overlay and
  production release definition.
- `awebai/bdh` is authoritative for Go CLI development and releases from
  v0.12.0 onward; `beadhub/bdh` preserves releases through v0.11.7.
- `beadhub/beadhub-cloud` remains the compatibility image-publishing mirror
  during the revival release. It is not a second development authority.
- The current product strategy lives outside the runtime repositories in the
  awebai strategy library.

Do not transfer, rename, archive, or force-push a compatibility repository as
part of ordinary feature work. A controlled release migration must first prove
the replacement URL, package, and rollback path.
