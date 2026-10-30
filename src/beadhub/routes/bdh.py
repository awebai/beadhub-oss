"""bdh coordination endpoints.

These endpoints are used by the `bdh` CLI wrapper to:
- preflight/record command execution (`POST /v1/bdh/command`)
- upload beads issue updates (`POST /v1/bdh/sync`)

They are intentionally thin wrappers around existing BeadHub primitives:
- auth comes from embedded aweb (`aw_sk_*` keys)
- bead sync uses `beadhub.beads_sync`
- notifications use the outbox pipeline in `beadhub.notifications`
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

if TYPE_CHECKING:
    from pgdbm import AsyncDatabaseManager

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis

from beadhub.auth import enforce_actor_binding, validate_workspace_id
from beadhub.aweb_context import resolve_aweb_identity_from_ids
from beadhub.aweb_introspection import get_identity_from_auth
from beadhub.beads_sync import (
    DEFAULT_BRANCH,
    BeadsSyncResult,
    _sync_issues_to_db,
    delete_issues_by_id,
    is_valid_alias,
    is_valid_canonical_origin,
    is_valid_human_name,
    validate_issues_from_list,
)
from beadhub.claims import (
    fetch_claimed_bead_ids,
    fetch_workspace_aliases,
    release_bead_claims,
    resolve_bead_id,
    upsert_claim,
)
from beadhub.routes.repos import canonicalize_git_url, extract_repo_name

from ..db import DatabaseInfra, get_db_infra
from ..events import BeadClaimedEvent, BeadUnclaimedEvent, publish_bead_status_events, publish_event
from ..jsonl import JSONLParseError, parse_jsonl
from ..notifications import process_notification_outbox, record_notification_intents
from ..presence import get_workspace_id_by_alias
from ..redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/bdh", tags=["bdh"])

MAX_JSONL_SIZE = 10 * 1024 * 1024  # 10MB
MAX_ISSUES_COUNT = 10000
MAX_JSON_DEPTH = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_command_line(command_line: str) -> tuple[Optional[str], list[str], Optional[str]]:
    """Return (command, bead_ids, status) best-effort, or (None, [], None).

    bead_ids are the ids exactly as typed, which may be short or partial forms
    that bd resolved (`resolve_bead_id` resolves them the same way): the
    tokens right after the command, up to the first flag. bdh joins bd's arguments with spaces, so a quoted
    flag value arrives as several tokens; stopping at the first flag keeps
    those words out of the ids.
    """

    parts = command_line.split()
    if not parts:
        return None, [], None
    cmd = parts[0].strip()
    bead_ids: list[str] = []
    status: Optional[str] = None
    if cmd in ("update", "close", "delete", "reopen"):
        for part in parts[1:]:
            if part.startswith("-"):
                break
            bead_ids.append(part)

    if cmd == "update":
        # Explicit status wins if both forms somehow appear. A successful
        # modern beads `--claim` mutation is equivalent to in_progress.
        claim_requested = "--claim" in parts
        for i, p in enumerate(parts):
            if p == "--status" and i + 1 < len(parts):
                status = parts[i + 1].strip()
                break
            if p.startswith("--status="):
                status = p.split("=", 1)[1].strip()
                break
        if status is None and claim_requested:
            status = "in_progress"

    return cmd, bead_ids, status


async def _resolve_bead_ids(
    db_infra: DatabaseInfra, project_id: str, raw_ids: list[str]
) -> list[str]:
    """Resolve command-line ids to full bead ids, dropping those that don't resolve."""
    bead_ids: list[str] = []
    for raw_id in raw_ids:
        bead_id = await resolve_bead_id(db_infra, project_id, raw_id)
        if bead_id is not None and bead_id not in bead_ids:
            bead_ids.append(bead_id)
    return bead_ids


def _claim_conflict_reason(conflicts: list[tuple[str, str, str]]) -> str:
    """Describe (bead_id, alias, human_name) conflicts for the bdh client."""
    return "; ".join(
        f"{bead_id} is being worked on by {alias} ({human_name})"
        for bead_id, alias, human_name in conflicts
    )


async def _ensure_workspace_alive_or_410(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    server_db = db_infra.get_manager("server")
    row = await server_db.fetch_one(
        """
        SELECT workspace_id, alias, human_name, role, deleted_at
        FROM {{tables.workspaces}}
        WHERE workspace_id = $1 AND project_id = $2
        """,
        UUID(workspace_id),
        UUID(project_id),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if row.get("deleted_at") is not None:
        raise HTTPException(status_code=410, detail="Workspace was deleted")
    return row


async def _touch_workspace_last_seen(
    db_infra: DatabaseInfra,
    *,
    project_id: str,
    workspace_id: str,
    human_name: str,
    role: Optional[str],
) -> None:
    server_db = db_infra.get_manager("server")
    await server_db.execute(
        """
        UPDATE {{tables.workspaces}}
        SET last_seen_at = $3,
            human_name = $4,
            role = $5
        WHERE workspace_id = $1 AND project_id = $2 AND deleted_at IS NULL
        """,
        UUID(workspace_id),
        UUID(project_id),
        _now(),
        human_name,
        role,
    )


async def _list_beads_in_progress(
    db_infra: DatabaseInfra, *, project_id: str
) -> list[dict[str, Any]]:
    server_db = db_infra.get_manager("server")
    rows = await server_db.fetch_all(
        """
        SELECT bead_id, workspace_id, alias, human_name, claimed_at
        FROM {{tables.bead_claims}}
        WHERE project_id = $1
        ORDER BY claimed_at DESC
        LIMIT 200
        """,
        UUID(project_id),
    )
    return [
        {
            "bead_id": r["bead_id"],
            "workspace_id": str(r["workspace_id"]),
            "alias": r["alias"],
            "human_name": r["human_name"],
            "started_at": r["claimed_at"].isoformat(),
            "title": None,
            "role": None,
        }
        for r in rows
    ]


async def _get_bead_title(
    beads_db: AsyncDatabaseManager, project_id: str, bead_id: str
) -> str | None:
    """Look up the title of a bead from the issues table."""
    row = await beads_db.fetch_one(
        "SELECT title FROM {{tables.beads_issues}} "
        "WHERE project_id = $1 AND bead_id = $2 ORDER BY synced_at DESC LIMIT 1",
        UUID(project_id),
        bead_id,
    )
    return row["title"] if row else None


async def _get_bead_titles(
    beads_db: AsyncDatabaseManager, project_id: str, bead_ids: list[str]
) -> dict[str, str | None]:
    """Batch look up titles for multiple beads. Returns {bead_id: title}."""
    if not bead_ids:
        return {}
    rows = await beads_db.fetch_all(
        "SELECT DISTINCT ON (bead_id) bead_id, title FROM {{tables.beads_issues}} "
        "WHERE project_id = $1 AND bead_id = ANY($2) ORDER BY bead_id, synced_at DESC",
        UUID(project_id),
        bead_ids,
    )
    return {row["bead_id"]: row["title"] for row in rows}


async def ensure_repo(
    db: DatabaseInfra,
    project_id: UUID,
    origin_url: str,
) -> UUID:
    """Ensure a repo exists for the given project and origin.

    Returns the repo_id (existing or newly created).
    """
    canonical_origin = canonicalize_git_url(origin_url)
    repo_name = extract_repo_name(canonical_origin)

    server_db = db.get_manager("server")
    # Also clear deleted_at to undelete soft-deleted repos when re-registered
    result = await server_db.fetch_one(
        """
        INSERT INTO {{tables.repos}} (project_id, origin_url, canonical_origin, name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (project_id, canonical_origin)
        DO UPDATE SET origin_url = EXCLUDED.origin_url, deleted_at = NULL
        RETURNING id
        """,
        project_id,
        origin_url,
        canonical_origin,
        repo_name,
    )
    return result["id"]


async def upsert_workspace(
    db: DatabaseInfra,
    workspace_id: str,
    project_id: UUID,
    repo_id: UUID,
    alias: str,
    human_name: str,
    role: Optional[str] = None,
    hostname: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> None:
    """Upsert workspace into persistent workspaces table.

    Creates or updates the workspace record. The workspace_id is the constant
    identifier. project_id, repo_id, alias, hostname, and workspace_path are
    immutable after creation (hostname/workspace_path can be set once if NULL).
    Only human_name, role, current_branch, deleted_at, and last_seen_at can be updated.

    last_seen_at is updated on every bdh command to track workspace activity.
    """
    server_db = db.get_manager("server")
    await server_db.execute(
        """
        INSERT INTO {{tables.workspaces}} (workspace_id, project_id, repo_id, alias, human_name, role, hostname, workspace_path, last_seen_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (workspace_id) DO UPDATE SET
            human_name = EXCLUDED.human_name,
            role = COALESCE(EXCLUDED.role, {{tables.workspaces}}.role),
            hostname = COALESCE({{tables.workspaces}}.hostname, EXCLUDED.hostname),
            workspace_path = COALESCE({{tables.workspaces}}.workspace_path, EXCLUDED.workspace_path),
            last_seen_at = NOW(),
            updated_at = NOW()
        """,
        workspace_id,
        project_id,
        repo_id,
        alias,
        human_name,
        role,
        hostname,
        workspace_path,
    )


async def check_alias_collision(
    db: DatabaseInfra,
    redis: Redis,
    project_id: UUID,
    workspace_id: str,
    alias: str,
) -> Optional[str]:
    """Check if alias is already used by another workspace within the same project.

    Aliases are unique per project (not globally). Projects are tenant boundaries
    with no cross-project communication, so per-project uniqueness is sufficient.

    Returns:
        The workspace_id using this alias if collision, None if available.
    """
    server_db = db.get_manager("server")

    # Check workspaces table first (authoritative source)
    row = await server_db.fetch_one(
        """
        SELECT workspace_id
        FROM {{tables.workspaces}}
        WHERE project_id = $1 AND alias = $2 AND workspace_id != $3 AND deleted_at IS NULL
        LIMIT 1
        """,
        project_id,
        alias,
        UUID(workspace_id),
    )
    if row:
        return str(row["workspace_id"])

    # Also check bead_claims for another workspace with same alias
    # (handles race conditions before workspace is persisted)
    row = await server_db.fetch_one(
        """
        SELECT DISTINCT workspace_id
        FROM {{tables.bead_claims}}
        WHERE project_id = $1 AND alias = $2 AND workspace_id != $3
        LIMIT 1
        """,
        project_id,
        alias,
        UUID(workspace_id),
    )
    if row:
        return str(row["workspace_id"])

    # Check Redis presence for another workspace with same alias
    # Uses O(1) secondary index instead of SCAN
    colliding_workspace = await get_workspace_id_by_alias(redis, str(project_id), alias)
    if colliding_workspace and colliding_workspace != workspace_id:
        return colliding_workspace

    return None


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    repo_id: str | None = None
    alias: str = Field(..., min_length=1, max_length=64)
    human_name: str = Field(..., min_length=0, max_length=64)
    repo_origin: str = Field(..., min_length=1, max_length=2048)
    role: str | None = Field(default=None, max_length=50)
    command_line: str = Field(..., min_length=1, max_length=8192)

    @field_validator("workspace_id")
    @classmethod
    def _validate_workspace_id(cls, v: str) -> str:
        return validate_workspace_id(v)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
        if not is_valid_alias(v):
            raise ValueError("Invalid alias format")
        return v

    @field_validator("human_name")
    @classmethod
    def _validate_human_name(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not is_valid_human_name(v):
            raise ValueError("Invalid human_name format")
        return v


class CommandContext(BaseModel):
    messages_waiting: int = 0
    beads_in_progress: list[dict[str, Any]] = Field(default_factory=list)


class CommandResponse(BaseModel):
    approved: bool
    reason: str = ""
    context: CommandContext | None = None


@router.post("/command", response_model=CommandResponse)
async def command(
    request: Request,
    payload: CommandRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
) -> CommandResponse:
    identity = await get_identity_from_auth(request, db_infra)
    project_id = identity.project_id

    enforce_actor_binding(identity, payload.workspace_id)

    # Ensure workspace exists, belongs to project, and is not deleted (410).
    await _ensure_workspace_alive_or_410(
        db_infra, project_id=project_id, workspace_id=payload.workspace_id
    )

    await _touch_workspace_last_seen(
        db_infra,
        project_id=project_id,
        workspace_id=payload.workspace_id,
        human_name=payload.human_name or "",
        role=payload.role,
    )

    beads_in_progress = await _list_beads_in_progress(db_infra, project_id=project_id)

    # Check if this is a claim command and a bead is already claimed by another workspace.
    cmd, raw_ids, status = _parse_command_line(payload.command_line or "")
    if cmd == "update" and status == "in_progress" and raw_ids:
        conflicts = [
            (claim["bead_id"], claim["alias"], claim["human_name"])
            for bead_id in await _resolve_bead_ids(db_infra, project_id, raw_ids)
            for claim in beads_in_progress
            if claim["bead_id"] == bead_id and claim["workspace_id"] != payload.workspace_id
        ]
        if conflicts:
            return CommandResponse(
                approved=False,
                reason=_claim_conflict_reason(conflicts),
                context=CommandContext(messages_waiting=0, beads_in_progress=beads_in_progress),
            )

    return CommandResponse(
        approved=True,
        context=CommandContext(messages_waiting=0, beads_in_progress=beads_in_progress),
    )


class SyncStats(BaseModel):
    received: int = 0
    inserted: int = 0
    updated: int = 0
    deleted: int = 0


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(..., min_length=1)
    repo_id: str | None = None
    alias: str = Field(..., min_length=1, max_length=64)
    human_name: str = Field(..., min_length=0, max_length=64)
    repo_origin: str = Field(..., min_length=1, max_length=2048)
    role: str | None = Field(default=None, max_length=50)

    # Full sync mode
    issues_jsonl: str | None = Field(default=None, max_length=MAX_JSONL_SIZE)

    # Incremental sync mode
    sync_mode: str | None = Field(default=None, max_length=32)
    changed_issues: str | None = Field(default=None, max_length=MAX_JSONL_SIZE)
    deleted_ids: list[str] = Field(default_factory=list)
    sync_protocol_version: int | None = None

    # Command context for claim attribution (best-effort)
    command_line: str | None = Field(default=None, max_length=8192)

    @field_validator("workspace_id")
    @classmethod
    def _validate_workspace_id(cls, v: str) -> str:
        return validate_workspace_id(v)

    @field_validator("alias")
    @classmethod
    def _validate_alias(cls, v: str) -> str:
        if not is_valid_alias(v):
            raise ValueError("Invalid alias format")
        return v

    @field_validator("human_name")
    @classmethod
    def _validate_human_name(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not is_valid_human_name(v):
            raise ValueError("Invalid human_name format")
        return v


class SyncResponse(BaseModel):
    synced: bool = True
    issues_count: int = 0
    context: CommandContext | None = None
    stats: SyncStats | None = None
    sync_protocol_version: int = 1
    conflicts: list[str] = Field(default_factory=list)
    conflicts_count: int = 0
    claim_rejected: bool = False
    claim_rejected_reason: str = ""


@router.post("/sync", response_model=SyncResponse)
async def sync(
    request: Request,
    payload: SyncRequest,
    db_infra: DatabaseInfra = Depends(get_db_infra),
    redis: Redis = Depends(get_redis),
) -> SyncResponse:
    identity = await get_identity_from_auth(request, db_infra)
    project_id = identity.project_id

    enforce_actor_binding(identity, payload.workspace_id)

    # Standalone bearer keys must retain the full aweb lifecycle guard. Resolve
    # it before touching workspace, bead, claim, or notification state. Cloud
    # proxy identities are already authenticated by the signed wrapper context.
    bearer_sender = None
    if identity.auth_mode == "bearer":
        bearer_sender = await resolve_aweb_identity_from_ids(
            db_infra,
            project_id=identity.project_id,
            agent_id=identity.agent_id or "",
        )

    await _ensure_workspace_alive_or_410(
        db_infra, project_id=project_id, workspace_id=payload.workspace_id
    )

    # Touch workspace activity for "gone workspace" and status displays.
    await _touch_workspace_last_seen(
        db_infra,
        project_id=project_id,
        workspace_id=payload.workspace_id,
        human_name=payload.human_name or "",
        role=payload.role,
    )

    canonical_origin = canonicalize_git_url(payload.repo_origin)
    if not is_valid_canonical_origin(canonical_origin):
        raise HTTPException(status_code=422, detail="Invalid repo_origin")

    beads_db = db_infra.get_manager("beads")

    mode = (payload.sync_mode or "full").strip().lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(status_code=422, detail="sync_mode must be 'full' or 'incremental'")

    received = 0
    inserted = 0
    updated = 0
    deleted = 0
    deleted_titles: dict[str, str | None] = {}

    result: Optional[BeadsSyncResult] = None
    if mode == "full":
        body = (payload.issues_jsonl or "").strip()
        if not body:
            raise HTTPException(status_code=422, detail="issues_jsonl is required for full sync")
        try:
            issues_raw = parse_jsonl(body, max_depth=MAX_JSON_DEPTH, max_count=MAX_ISSUES_COUNT)
        except JSONLParseError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        issues = validate_issues_from_list(issues_raw)
        received = len(issues)
        result = await _sync_issues_to_db(
            issues,
            beads_db,
            project_id=project_id,
            repo=canonical_origin,
            branch=DEFAULT_BRANCH,
        )
        inserted = result.issues_added
        updated = result.issues_updated
    else:
        if (
            payload.changed_issues is None or payload.changed_issues.strip() == ""
        ) and not payload.deleted_ids:
            raise HTTPException(
                status_code=422, detail="incremental sync requires changes or deletions"
            )

        if payload.changed_issues is not None and payload.changed_issues.strip():
            try:
                issues_raw = parse_jsonl(
                    payload.changed_issues, max_depth=MAX_JSON_DEPTH, max_count=MAX_ISSUES_COUNT
                )
            except JSONLParseError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            issues = validate_issues_from_list(issues_raw)
            received = len(issues)
            result = await _sync_issues_to_db(
                issues,
                beads_db,
                project_id=project_id,
                repo=canonical_origin,
                branch=DEFAULT_BRANCH,
            )
            inserted = result.issues_added
            updated = result.issues_updated

    # Resolve the bd command's ids after this sync's beads are applied and
    # before its deletions, so a bead this sync creates or deletes resolves.
    cmd, raw_ids, status = _parse_command_line(payload.command_line or "")
    bead_ids = await _resolve_bead_ids(db_infra, project_id, raw_ids)

    if mode == "incremental" and payload.deleted_ids:
        # Pre-fetch titles before deletion so events can include them.
        deleted_titles = await _get_bead_titles(beads_db, project_id, payload.deleted_ids)
        deleted = await delete_issues_by_id(
            beads_db,
            project_id=project_id,
            bead_ids=payload.deleted_ids,
            repo=canonical_origin,
            branch=DEFAULT_BRANCH,
        )

    # Update claims based on the bd command that succeeded (best-effort).
    claim_conflicts: list[tuple[str, str, str]] = []

    # Lazy project_slug for event enrichment (only queried if needed).
    _slug_cache: list[str | None] = []  # empty = not yet fetched

    async def _get_project_slug() -> str | None:
        if not _slug_cache:
            server_db = db_infra.get_manager("server")
            row = await server_db.fetch_one(
                "SELECT slug FROM {{tables.projects}} WHERE id = $1",
                UUID(project_id),
            )
            _slug_cache.append(row["slug"] if row else None)
        return _slug_cache[0]

    if cmd == "update" and status == "in_progress":
        for bead_id in bead_ids:
            claim_result = await upsert_claim(
                db_infra,
                project_id=project_id,
                workspace_id=payload.workspace_id,
                alias=payload.alias,
                human_name=payload.human_name or "",
                bead_id=bead_id,
            )
            if claim_result.conflict:
                claim_conflicts.append(
                    (
                        bead_id,
                        claim_result.conflict["alias"],
                        claim_result.conflict["human_name"],
                    )
                )
            if claim_result.created:
                title = await _get_bead_title(beads_db, project_id, bead_id)
                await publish_event(
                    redis,
                    BeadClaimedEvent(
                        workspace_id=payload.workspace_id,
                        project_slug=await _get_project_slug(),
                        bead_id=bead_id,
                        alias=payload.alias,
                        title=title,
                    ),
                )

    # A bead that is closed, deleted or no longer in progress keeps no claims,
    # from any workspace: release them whether the command line or the synced
    # beads say so, so a claim can't outlive its bead.
    release_ids: list[str] = []
    if cmd in ("close", "delete") or (cmd == "update" and status and status != "in_progress"):
        release_ids.extend(bead_ids)
    if result is not None:
        release_ids.extend(
            change.bead_id
            for change in result.status_changes
            if change.new_status == "closed"
            or (change.old_status == "in_progress" and change.new_status != "in_progress")
        )
    release_ids.extend(payload.deleted_ids)
    claimed_ids = await fetch_claimed_bead_ids(db_infra, project_id, release_ids)
    for bead_id in dict.fromkeys(release_ids):
        if bead_id not in claimed_ids:
            continue
        claimant_ids = await release_bead_claims(
            db_infra,
            project_id=project_id,
            bead_id=bead_id,
        )
        if claimant_ids:
            if bead_id in deleted_titles:
                title = deleted_titles[bead_id]
            else:
                title = await _get_bead_title(beads_db, project_id, bead_id)
            claimant_aliases = await fetch_workspace_aliases(db_infra, project_id, claimant_ids)
            slug = await _get_project_slug()
            for cid in claimant_ids:
                await publish_event(
                    redis,
                    BeadUnclaimedEvent(
                        workspace_id=cid,
                        project_slug=slug,
                        bead_id=bead_id,
                        alias=claimant_aliases.get(cid, ""),
                        title=title,
                    ),
                )

    # Record notification intents in outbox, then process them.
    notifications_sent = 0
    notifications_failed = 0
    if result is not None and result.status_changes:
        await record_notification_intents(result.status_changes, project_id, db_infra)
        notifications_sent, notifications_failed = await process_notification_outbox(
            project_id, db_infra
        )
        if bearer_sender is not None:
            project_slug = bearer_sender.project_slug
        else:
            project_slug = await _get_project_slug()
        await publish_bead_status_events(
            redis,
            workspace_id=payload.workspace_id,
            project_slug=project_slug,
            status_changes=result.status_changes,
            alias=payload.alias,
        )

    # Update audit log (best-effort; don't fail the sync on logging issues).
    try:
        server_db = db_infra.get_manager("server")
        await server_db.execute(
            """
            INSERT INTO {{tables.audit_log}} (project_id, event_type, details)
            VALUES ($1, $2, $3::jsonb)
            """,
            UUID(project_id),
            "bdh_sync",
            json.dumps(
                {
                    "project_id": project_id,
                    "repo": canonical_origin,
                    "mode": mode,
                    "received": received,
                    "inserted": inserted,
                    "updated": updated,
                    "deleted": deleted,
                    "notifications_sent": notifications_sent,
                    "notifications_failed": notifications_failed,
                }
            ),
        )
    except Exception:
        logger.exception("Failed to write audit log for bdh sync")

    # Count total issues for this (project, repo, branch) after sync.
    count_row = await beads_db.fetch_one(
        """
        SELECT COUNT(*) AS c
        FROM {{tables.beads_issues}}
        WHERE project_id = $1 AND repo = $2 AND branch = $3
        """,
        UUID(project_id),
        canonical_origin,
        DEFAULT_BRANCH,
    )
    issues_count = int(count_row["c"]) if count_row else 0

    sync_conflicts = sorted(result.conflicts) if result is not None else []
    resp = SyncResponse(
        synced=not sync_conflicts,
        issues_count=issues_count,
        stats=SyncStats(received=received, inserted=inserted, updated=updated, deleted=deleted),
        sync_protocol_version=1,
        conflicts=sync_conflicts,
        conflicts_count=len(sync_conflicts),
    )
    if claim_conflicts:
        resp.claim_rejected = True
        resp.claim_rejected_reason = _claim_conflict_reason(claim_conflicts)
    return resp
