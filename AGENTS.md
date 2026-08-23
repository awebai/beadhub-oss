# BeadHub OSS agent instructions

Active team instructions supplied by the assigned aweb workspace are
authoritative. If a profile or repository copy disagrees with those active
instructions, stop and report the conflict; do not choose silently.

## Project context

Read [REPOSITORY.md](REPOSITORY.md) before changing repository boundaries and
[docs/sot.md](docs/sot.md) before changing the inherited implementation.

BeadHub is a federated aweb server with a beads-shaped coordination surface.
This repository owns the BeadHub-specific OSS adapter, dashboard, self-host
packaging, and public federation documentation. Identity, mail, chat, wake,
presence, and federation primitives belong in `awebai/aweb`, not in a BeadHub
fork. The compatible Go client is released from `beadhub/bdh`.

The recovered code predates the federation rebase. During Phase 0, prefer the
smallest compatibility-preserving fixes needed to restore activation and a
rebuildable service. Do not start profile-first onboarding, Team Builder,
marketplace work, runtime ownership redesign, or unrelated service extraction.

## Stack and structure

- Python 3.12+, FastAPI, PostgreSQL through pgdbm, Redis, and uv.
- `src/beadhub/`: server and route implementation.
- `frontend/packages/dashboard/`: reusable dashboard package.
- `tests/`: Python regression coverage.
- `docs/`: implementation and operator documentation.

Use pgdbm's existing fixtures and table-template conventions. Every persistent
query is project-scoped; preserve actor binding and soft-delete invariants.

## Development

```bash
uv run beadhub
uv run pytest
```

Run the minimum meaningful test target once. Repeat a long suite only for a
specific unresolved risk.

## Coordination

This project uses `aw`, not the retired `bdh` coordination control plane.
Coordination identity comes from `.aw/workspace.yaml` in the assigned worktree.
Never run `aw` from another workspace or copy another workspace's identity.

At the start of work, in this order:

```bash
aw workspace status
aw mail inbox
aw chat pending
aw work ready
```

Use mail for non-blocking handoffs and chat only when a synchronous answer is
required. Process waiting chats before claiming new work. Keep task state and
dependencies in `aw`, not in local TODO files or the inherited `.beads` data.

For Markdown messages, write a body file, read it back to ensure shell-sensitive
characters survived, and use the relevant `--body-file` option.

## Review and landing

- Stay on the assigned branch/worktree; do not make temporary branches.
- Preserve unrelated user changes in dirty trees.
- Every task requires an independent review before closure.
- Reviewers ACK a SHA and state how many non-merge commits they reviewed.
- A reviewer suggestion is new, unreviewed work until a separate review covers
  its implementation.
- Merge current `origin/main` before final review/handoff, compare the reviewed
  three-dot diff, and inspect every commit that would land.
- Never push unreviewed work to main. If unreviewed work already landed, review
  it in place rather than reverting correct code merely for process reasons.

Shipping correct accumulated work is the priority. Keep a runner-independent
build/stage/publish path and preserve an explicit human risk override for an
urgent release or runner outage.
