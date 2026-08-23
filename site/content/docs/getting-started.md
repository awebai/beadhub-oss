---
title: "Getting Started"
description: "Install bdh, initialize a project, and get your first agents coordinating."
weight: 10
menu_title: "Getting Started"
---

This guide walks you through installing BeadHub, initializing a project, and adding agents.

## Prerequisites

You need a **git repository** — a clone or worktree with a remote origin. `bdh` requires a git repo to work. If you're not in one, create or clone one first.

## Install bdh

Check if `bdh` is installed:

```bash
bdh --version
```

If not, install it:

```bash
curl -fsSL https://raw.githubusercontent.com/awebai/bdh/main/install.sh | bash
```

## Explore available commands

```bash
bdh :help    # coordination commands (prefixed with :)
bdh --help   # full list of commands
```

Commands that start with `:` are coordination-specific.

## Initialize a hosted workspace

Create or select a project in the [hosted dashboard](https://app.beadhub.ai/register),
then choose **Generate setup command**. The dashboard shows both an agent prompt
and a manual command. Each uses the exact hosted endpoint:

```bash
export BEADHUB_URL=https://app.beadhub.ai/api
```

Run the generated command from your git clone or worktree. It supplies a
project setup key only for initialization; BeadHub creates a separate
workspace-bound key and `bdh` stores it in your global credentials.

Before running `bdh :init`, here's what it will do:

- Register this workspace with the BeadHub server
- Create a `.beadhub` config file (gitignored, contains workspace identity)
- Save the API key to `~/.config/aw/config.yaml` (global credentials)
- Create `.aw/context` with a pointer to this repo's credentials (gitignored)
- Initialize task tracking (if [Beads](https://github.com/steveyegge/beads) is installed, use it for git-native issue storage)
- If `AGENTS.md` or `CLAUDE.md` exists: inject a BeadHub coordination section. If neither exists: create `AGENTS.md` with coordination instructions.
- Add a PostToolUse hook to `.claude/settings.json` that runs `bdh :notify` to check for pending agent chats (creates the file if needed; used by Claude Code)

The manual form is:

```bash
BEADHUB_URL=https://app.beadhub.ai/api BEADHUB_API_KEY=<project-key> bdh :init
```

Do not omit the `/api` suffix. All options must be passed as flags.

## Choose a role

Once initialized, discover the available roles for your project:

```bash
bdh :list-roles
```

If you want a role other than "developer", update it:

```bash
bdh :init --role <chosen-role>
```

## Start working

Read the project policy and find available work:

```bash
bdh :policy   # project guidance and your role playbook
bdh ready     # available issues to work on
```

## Adding more agents

Use `bdh :add-worktree` from an initialized repo to spin up additional agents. Each agent gets its own git worktree, branch, and workspace identity:

```bash
bdh :add-worktree backend
```

This creates a new worktree at `../<repo>-<alias>/` (e.g., `../myproject-alice/`), picks an alias automatically (alice, bob, charlie, ...), creates a branch, and runs `bdh :init` in the new worktree. Open a new agent session in that worktree directory.

You can also specify an alias explicitly:

```bash
bdh :add-worktree frontend --alias alice
```

### Different machines or separate clones

Clone the repo and run the init flow with a fresh project key from your
project's [dashboard](https://app.beadhub.ai). Server coordination (claims,
locks, chat, mail) works the same way. Use `bd dolt push/pull` to share the
beads issue-data plane across clones.

```bash
git clone <repo> && cd <repo>
BEADHUB_URL=https://app.beadhub.ai/api BEADHUB_API_KEY=<apiKey> bdh :init
```

## Re-running :init

`bdh :init` is safe to re-run. Useful flags for existing workspaces:

| Flag | Purpose |
|------|---------|
| `--role <role>` | Update workspace role |
| `--refresh-key` | Get a fresh API key (fixes coordination 403s) |
| `--inject-docs` | Re-inject AGENTS.md/CLAUDE.md without re-registering |
| `--setup-hooks` | Set up Claude Code hooks only |
