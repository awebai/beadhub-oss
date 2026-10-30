"""Bead claim lifecycle operations.

Shared by the bdh sync handler (beads mode) and the mutation hooks
(native aweb-tasks mode).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from .db import DatabaseInfra

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimUpsertResult:
    """Outcome of an idempotent claim mutation."""

    created: bool
    conflict: Optional[dict[str, Any]] = None


async def fetch_workspace_aliases(
    db_infra: "DatabaseInfra", project_id: str, workspace_ids: list[str]
) -> dict[str, str]:
    """Return {workspace_id: alias} for a list of workspace IDs.

    Skips deleted workspaces (they return alias="" via caller fallback).
    """
    if not workspace_ids:
        return {}
    server_db = db_infra.get_manager("server")
    rows = await server_db.fetch_all(
        "SELECT workspace_id, alias FROM {{tables.workspaces}} "
        "WHERE project_id = $1 AND workspace_id = ANY($2) AND deleted_at IS NULL",
        UUID(project_id),
        [UUID(ws_id) for ws_id in workspace_ids],
    )
    return {str(row["workspace_id"]): row["alias"] for row in rows}


async def fetch_claimed_bead_ids(
    db_infra: "DatabaseInfra", project_id: str, bead_ids: list[str]
) -> set[str]:
    """Return the subset of bead_ids that have at least one claim in the project."""
    if not bead_ids:
        return set()
    server_db = db_infra.get_manager("server")
    rows = await server_db.fetch_all(
        "SELECT DISTINCT bead_id FROM {{tables.bead_claims}} "
        "WHERE project_id = $1 AND bead_id = ANY($2)",
        UUID(project_id),
        list(set(bead_ids)),
    )
    return {row["bead_id"] for row in rows}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_task_apex(
    db_infra: DatabaseInfra,
    project_id: str,
    task_ref: str,
    max_depth: int = 20,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Walk aweb tasks parent_task_id chain to find the root task.

    Falls back to aweb.tasks when beads_issues has no data (native mode).
    Returns (root_task_ref, None, None) since aweb tasks have no repo/branch.
    """
    aweb_db = db_infra.get_manager("aweb")

    # Look up the project slug for task_ref reconstruction
    project = await aweb_db.fetch_one(
        "SELECT slug FROM {{tables.projects}} WHERE project_id = $1 AND deleted_at IS NULL",
        UUID(project_id),
    )
    if not project:
        return None, None, None
    slug = project["slug"]

    # Parse task_number from task_ref (format: {slug}-{number:03d})
    prefix = slug + "-"
    if not task_ref.startswith(prefix):
        return None, None, None
    try:
        task_number = int(task_ref[len(prefix) :])
    except ValueError:
        return None, None, None

    current = await aweb_db.fetch_one(
        """
        SELECT task_id, task_number, parent_task_id
        FROM {{tables.tasks}}
        WHERE project_id = $1 AND task_number = $2 AND deleted_at IS NULL
        """,
        UUID(project_id),
        task_number,
    )
    if not current:
        return None, None, None

    # Walk parent chain to root
    depth = 0
    while current.get("parent_task_id") and depth < max_depth:
        parent = await aweb_db.fetch_one(
            """
            SELECT task_id, task_number, parent_task_id
            FROM {{tables.tasks}}
            WHERE task_id = $1 AND deleted_at IS NULL
            """,
            current["parent_task_id"],
        )
        if not parent:
            break
        current = parent
        depth += 1

    apex_ref = f"{slug}-{current['task_number']:03d}"
    return apex_ref, None, None


async def resolve_claim_apex(
    db_infra: DatabaseInfra,
    project_id: str,
    bead_id: str,
    max_depth: int = 20,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Resolve the apex for a bead by walking parent_id links.

    Returns (apex_bead_id, apex_repo_name, apex_branch). If the bead isn't found
    in beads_issues, returns (None, None, None).
    """
    beads_db = db_infra.get_manager("beads")
    current = await beads_db.fetch_one(
        """
        SELECT bead_id, repo, branch, parent_id
        FROM {{tables.beads_issues}}
        WHERE project_id = $1 AND bead_id = $2
        ORDER BY synced_at DESC
        LIMIT 1
        """,
        UUID(project_id),
        bead_id,
    )
    if not current:
        return await _resolve_task_apex(db_infra, project_id, bead_id, max_depth)

    depth = 0
    while current.get("parent_id") and depth < max_depth:
        parent = current["parent_id"]
        if isinstance(parent, str):
            try:
                parent = json.loads(parent)
            except (json.JSONDecodeError, RecursionError):
                break
        if not isinstance(parent, dict):
            break
        parent_repo = parent.get("repo")
        parent_branch = parent.get("branch")
        parent_bead_id = parent.get("bead_id")
        if not parent_repo or not parent_branch or not parent_bead_id:
            break

        parent_row = await beads_db.fetch_one(
            """
            SELECT bead_id, repo, branch, parent_id
            FROM {{tables.beads_issues}}
            WHERE project_id = $1
              AND repo = $2
              AND branch = $3
              AND bead_id = $4
            ORDER BY synced_at DESC
            LIMIT 1
            """,
            UUID(project_id),
            parent_repo,
            parent_branch,
            parent_bead_id,
        )
        if not parent_row:
            break
        current = parent_row
        depth += 1

    return current["bead_id"], current["repo"], current["branch"]


async def upsert_claim(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    alias: str,
    human_name: str,
    bead_id: str,
) -> ClaimUpsertResult:
    """Attempt to claim a bead and distinguish creation from replay."""
    server_db = db_infra.get_manager("server")
    project_uuid = UUID(project_id)
    workspace_uuid = UUID(workspace_id)

    # Resolve apex (root parent) for this bead
    apex_bead_id, apex_repo_name, apex_branch = await resolve_claim_apex(
        db_infra, project_id, bead_id
    )

    async with server_db.transaction() as tx:
        # Serialize ordinary claim attempts for this project/bead before the
        # conflict check. Without a transaction-scoped lock, two transactions
        # can both observe no owner and insert different workspace rows.
        # hashtextextended returns a stable signed bigint suitable for a
        # PostgreSQL advisory lock; a collision only serializes unrelated
        # claims and cannot weaken exclusivity.
        await tx.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"{project_uuid}\x1f{bead_id}",
        )

        # Check if another workspace already holds this claim.
        existing = await tx.fetch_one(
            """
            SELECT workspace_id, alias, human_name
            FROM {{tables.bead_claims}}
            WHERE project_id = $1 AND bead_id = $2 AND workspace_id != $3
            """,
            project_uuid,
            bead_id,
            workspace_uuid,
        )
        if existing:
            return ClaimUpsertResult(
                created=False,
                conflict={
                    "workspace_id": str(existing["workspace_id"]),
                    "alias": existing["alias"],
                    "human_name": existing["human_name"],
                },
            )

        row = await tx.fetch_one(
            """
            INSERT INTO {{tables.bead_claims}} (
                project_id, workspace_id, alias, human_name, bead_id,
                apex_bead_id, apex_repo_name, apex_branch, claimed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (project_id, bead_id, workspace_id)
            DO UPDATE SET
                alias = EXCLUDED.alias,
                human_name = EXCLUDED.human_name,
                apex_bead_id = EXCLUDED.apex_bead_id,
                apex_repo_name = EXCLUDED.apex_repo_name,
                apex_branch = EXCLUDED.apex_branch
            RETURNING (xmax = 0) AS created
            """,
            project_uuid,
            workspace_uuid,
            alias,
            human_name,
            bead_id,
            apex_bead_id,
            apex_repo_name,
            apex_branch,
            _now(),
        )

    # Update workspace focus_apex fields for team status display
    if apex_bead_id:
        await server_db.execute(
            """
            UPDATE {{tables.workspaces}}
            SET focus_apex_bead_id = $1,
                focus_apex_repo_name = $2,
                focus_apex_branch = $3,
                focus_updated_at = NOW(),
                updated_at = NOW()
            WHERE project_id = $4 AND workspace_id = $5
            """,
            apex_bead_id,
            apex_repo_name,
            apex_branch,
            project_uuid,
            workspace_uuid,
        )

    return ClaimUpsertResult(created=bool(row and row["created"]))


async def release_bead_claims(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    bead_id: str,
    workspace_id: str | None = None,
) -> list[str]:
    """Release claims on a bead and update affected workspaces' focus.

    If workspace_id is provided, only that workspace's claim is removed.
    If workspace_id is None, ALL claims on the bead are removed (used when
    a bead is closed/deleted, since any workspace's claim becomes stale).

    Returns the workspace_id strings of affected claimants.
    """
    server_db = db_infra.get_manager("server")
    async with server_db.transaction() as tx:
        # Find affected workspaces before deleting.
        if workspace_id:
            affected_ws_ids = [UUID(workspace_id)]
            await tx.execute(
                """
                DELETE FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND workspace_id = $2 AND bead_id = $3
                """,
                UUID(project_id),
                UUID(workspace_id),
                bead_id,
            )
        else:
            rows = await tx.fetch_all(
                """
                DELETE FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND bead_id = $2
                RETURNING workspace_id
                """,
                UUID(project_id),
                bead_id,
            )
            affected_ws_ids = [row["workspace_id"] for row in rows]

        # Update each affected workspace's focus to its next active claim.
        for ws_id in affected_ws_ids:
            next_claim = await tx.fetch_one(
                """
                SELECT apex_bead_id, apex_repo_name, apex_branch
                FROM {{tables.bead_claims}}
                WHERE project_id = $1 AND workspace_id = $2
                ORDER BY claimed_at DESC
                LIMIT 1
                """,
                UUID(project_id),
                ws_id,
            )
            await tx.execute(
                """
                UPDATE {{tables.workspaces}}
                SET focus_apex_bead_id = $1,
                    focus_apex_repo_name = $2,
                    focus_apex_branch = $3,
                    focus_updated_at = NOW(),
                    updated_at = NOW()
                WHERE project_id = $4 AND workspace_id = $5
                """,
                next_claim["apex_bead_id"] if next_claim else None,
                next_claim["apex_repo_name"] if next_claim else None,
                next_claim["apex_branch"] if next_claim else None,
                UUID(project_id),
                ws_id,
            )

    return [str(ws_id) for ws_id in affected_ws_ids]


async def resolve_bead_id(db_infra: DatabaseInfra, project_id: str, raw_id: str) -> Optional[str]:
    """Resolve a bead id as typed on a bd command line to the bead's full id.

    Follows bd's own resolution (ResolvePartialID, beads v1.3.1,
    internal/utils/id_parser.go), against the project's synced beads:

    1. the exact id;
    2. the id without its prefix: a bead whose id is `<prefix>-<raw_id>`;
    3. a partial id: with a prefix, a bead id that starts with it; without
       one, a bead whose hash (the part after the prefix) starts with it.

    The first rule that matches decides. Beads are stored per repo, so the
    same id in several repos is one bead. When a rule matches several beads,
    or nothing matches, this logs a warning and returns None.
    """
    beads_db = db_infra.get_manager("beads")
    rows = await beads_db.fetch_all(
        "SELECT DISTINCT bead_id FROM {{tables.beads_issues}} "
        "WHERE project_id = $1 AND strpos(bead_id, $2) > 0",
        UUID(project_id),
        raw_id,
    )
    candidates = [row["bead_id"] for row in rows]
    if raw_id in candidates:
        return raw_id

    matches = [bead_id for bead_id in candidates if bead_id.endswith("-" + raw_id)]
    if not matches:
        if "-" in raw_id:
            matches = [bead_id for bead_id in candidates if bead_id.startswith(raw_id)]
        else:
            matches = [
                bead_id for bead_id in candidates if bead_id.rsplit("-", 1)[-1].startswith(raw_id)
            ]

    if len(matches) == 1:
        return matches[0]
    if matches:
        logger.warning(
            "Bead id %r is ambiguous in project %s: it matches %s",
            raw_id,
            project_id,
            sorted(matches),
        )
    else:
        logger.warning("Bead id %r matches no bead in project %s", raw_id, project_id)
    return None
