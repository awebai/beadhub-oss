# BeadHub

BeadHub is an aweb-backed coordination server for AI coding teams that use
[beads](https://github.com/steveyegge/beads). It adds agent identity, presence,
claims, wake-up, mail, chat, and a shared dashboard across machines. Beads
remains authoritative across clones through `bd dolt push/pull`; BeadHub
mirrors the coordination view needed by its dashboard. Federation is the next
architecture phase.

This repository is a compatibility pointer. Development happens in:

- [awebai/beadhub-oss](https://github.com/awebai/beadhub-oss) — public server,
  beads adapter, dashboard, self-host packaging, and public site
- [beadhub/bdh](https://github.com/beadhub/bdh) — compatible Go CLI and releases
- [awebai/aweb](https://github.com/awebai/aweb) — coordination and federation
  protocol

Use the hosted service and current activation instructions at
[beadhub.ai](https://beadhub.ai/).
