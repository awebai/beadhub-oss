"""Claims carry the bead's full id, whatever form the bd command line used.

bd accepts a bead id without its project prefix, and a unique partial id.
The server resolves the id from the command line against the project's synced
beads before it claims, releases or conflict-checks, and releases a bead's
claims when a sync shows the bead leaving in_progress.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager, contextmanager

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from beadhub.api import create_app
from beadhub.beads_sync import _sync_issues_to_db
from beadhub.claims import resolve_bead_id

TEST_REDIS_URL = "redis://localhost:6379/15"
TEST_REPO_ORIGIN = "git@github.com:anthropic/beadhub.git"
OTHER_REPO_ORIGIN = "git@github.com:anthropic/beadhub-other.git"


def _jsonl(*rows: dict) -> str:
    return "\n".join(json.dumps(r) for r in rows) + "\n"


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@contextmanager
def resolver_warnings():
    """Collect warnings from beadhub.claims.

    A handler on the logger itself, because the app's startup replaces the
    root logger's handlers, pytest's caplog handler among them.
    """
    handler = _Records()
    claims_logger = logging.getLogger("beadhub.claims")
    claims_logger.addHandler(handler)
    try:
        yield handler.messages
    finally:
        claims_logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# resolve_bead_id
# ---------------------------------------------------------------------------


async def _seed(db_infra, project_id: str, bead_ids: list[str], repo: str = "github.com/a/b"):
    await _sync_issues_to_db(
        {bid: {"id": bid, "title": bid, "status": "open"} for bid in bead_ids},
        db_infra.get_manager("beads"),
        project_id=project_id,
        repo=repo,
    )


@pytest.mark.asyncio
async def test_resolve_exact_id(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12", "proj-abc12.1"])
    assert await resolve_bead_id(db_infra, project_id, "proj-abc12") == "proj-abc12"
    assert await resolve_bead_id(db_infra, project_id, "proj-abc12.1") == "proj-abc12.1"


@pytest.mark.asyncio
async def test_resolve_id_without_prefix_prefers_exact_suffix_over_child(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-t5dk", "proj-t5dk.1"])
    assert await resolve_bead_id(db_infra, project_id, "t5dk") == "proj-t5dk"
    assert await resolve_bead_id(db_infra, project_id, "t5dk.1") == "proj-t5dk.1"


@pytest.mark.asyncio
async def test_resolve_prefix_with_underscore(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["my_proj-4auv"])
    assert await resolve_bead_id(db_infra, project_id, "4auv") == "my_proj-4auv"
    assert await resolve_bead_id(db_infra, project_id, "4au") == "my_proj-4auv"
    assert await resolve_bead_id(db_infra, project_id, "my_proj-4au") == "my_proj-4auv"


@pytest.mark.asyncio
async def test_resolve_unique_partial_id(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12", "proj-xyz34"])
    assert await resolve_bead_id(db_infra, project_id, "abc") == "proj-abc12"
    assert await resolve_bead_id(db_infra, project_id, "proj-ab") == "proj-abc12"


@pytest.mark.asyncio
async def test_resolve_same_id_in_two_repos_is_one_bead(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12"], repo="github.com/a/one")
    await _seed(db_infra, project_id, ["proj-abc12"], repo="github.com/a/two")
    assert await resolve_bead_id(db_infra, project_id, "abc12") == "proj-abc12"
    assert await resolve_bead_id(db_infra, project_id, "abc") == "proj-abc12"


@pytest.mark.asyncio
async def test_resolve_ambiguous_suffix_returns_none_and_warns(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["one-x1y2", "two-x1y2"])
    with resolver_warnings() as warnings:
        assert await resolve_bead_id(db_infra, project_id, "x1y2") is None
    assert len(warnings) == 1
    assert project_id in warnings[0]
    assert "x1y2" in warnings[0]
    assert "ambiguous" in warnings[0]


@pytest.mark.asyncio
async def test_resolve_ambiguous_partial_returns_none_and_warns(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12", "proj-abd34", "proj-t5dk", "proj-t5dk.1"])
    with resolver_warnings() as warnings:
        assert await resolve_bead_id(db_infra, project_id, "ab") is None
        assert await resolve_bead_id(db_infra, project_id, "t5d") is None
    assert len(warnings) == 2
    assert all(project_id in w and "ambiguous" in w for w in warnings)


@pytest.mark.asyncio
async def test_resolve_unknown_returns_none_and_warns(db_infra):
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12"])
    with resolver_warnings() as warnings:
        assert await resolve_bead_id(db_infra, project_id, "zzz9") is None
    assert len(warnings) == 1
    assert project_id in warnings[0]
    assert "zzz9" in warnings[0]
    assert "no bead" in warnings[0]


@pytest.mark.asyncio
async def test_resolve_rejects_interior_and_prefix_part_matches(db_infra):
    """A partial id matches the start of the id's hash, as bd does, nothing else."""
    project_id = str(uuid.uuid4())
    await _seed(db_infra, project_id, ["proj-abc12"])
    with resolver_warnings() as warnings:
        assert await resolve_bead_id(db_infra, project_id, "bc12") is None
        assert await resolve_bead_id(db_infra, project_id, "pro") is None
        assert await resolve_bead_id(db_infra, project_id, "oj-abc12") is None
    assert len(warnings) == 3


@pytest.mark.asyncio
async def test_resolve_is_project_scoped(db_infra):
    project_id = str(uuid.uuid4())
    other_project_id = str(uuid.uuid4())
    await _seed(db_infra, other_project_id, ["proj-abc12"])
    with resolver_warnings() as warnings:
        assert await resolve_bead_id(db_infra, project_id, "proj-abc12") is None
        assert await resolve_bead_id(db_infra, project_id, "abc12") is None
    assert len(warnings) == 2


# ---------------------------------------------------------------------------
# /v1/bdh endpoints
# ---------------------------------------------------------------------------


class Project:
    """Two workspaces in one project, and helpers to drive the bdh endpoints."""

    def __init__(self, client: AsyncClient, alice: dict, bob: dict):
        self.client = client
        self.alice = alice
        self.bob = bob

    async def sync(self, ws: dict, *, command_line: str | None, **body) -> dict:
        payload = {
            "workspace_id": ws["workspace_id"],
            "repo_id": ws["repo_id"],
            "alias": ws["alias"],
            "human_name": ws["human_name"],
            "repo_origin": body.pop("repo_origin", TEST_REPO_ORIGIN),
            "role": "agent",
            **body,
        }
        if command_line is not None:
            payload["command_line"] = command_line
        resp = await self.client.post(
            "/v1/bdh/sync",
            headers={"Authorization": f"Bearer {ws['api_key']}"},
            json=payload,
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def full_sync(self, ws: dict, issues: list[dict], command_line: str | None, **body):
        return await self.sync(
            ws, command_line=command_line, sync_mode="full", issues_jsonl=_jsonl(*issues), **body
        )

    async def incremental_sync(
        self,
        ws: dict,
        changed: list[dict],
        command_line: str | None,
        deleted_ids: list[str] | None = None,
    ):
        body = {"sync_mode": "incremental", "deleted_ids": deleted_ids or []}
        if changed:
            body["changed_issues"] = _jsonl(*changed)
        return await self.sync(ws, command_line=command_line, **body)

    async def command(self, ws: dict, command_line: str) -> dict:
        resp = await self.client.post(
            "/v1/bdh/command",
            headers={"Authorization": f"Bearer {ws['api_key']}"},
            json={
                "workspace_id": ws["workspace_id"],
                "repo_id": ws["repo_id"],
                "alias": ws["alias"],
                "human_name": ws["human_name"],
                "repo_origin": TEST_REPO_ORIGIN,
                "role": "agent",
                "command_line": command_line,
            },
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    async def claims(self) -> list[tuple[str, str]]:
        resp = await self.client.get(
            "/v1/claims", headers={"Authorization": f"Bearer {self.alice['api_key']}"}
        )
        assert resp.status_code == 200, resp.text
        return sorted((c["bead_id"], c["alias"]) for c in resp.json()["claims"])


@pytest.fixture
def project(db_infra, init_workspace):
    @asynccontextmanager
    async def _project():
        redis = await Redis.from_url(TEST_REDIS_URL, decode_responses=True)
        try:
            await redis.ping()
        except Exception:
            pytest.skip("Redis is not available")
        await redis.flushdb()
        try:
            app = create_app(db_infra=db_infra, redis=redis, serve_frontend=False)
            async with LifespanManager(app):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    slug = f"claim-ids-{uuid.uuid4().hex[:8]}"
                    alice = await init_workspace(
                        client,
                        project_slug=slug,
                        repo_origin=TEST_REPO_ORIGIN,
                        alias="alice",
                        human_name="Alice",
                        role="agent",
                    )
                    bob = await init_workspace(
                        client,
                        project_slug=slug,
                        repo_origin=TEST_REPO_ORIGIN,
                        alias="bob",
                        human_name="Bob",
                        role="agent",
                    )
                    yield Project(client, alice, bob)
        finally:
            await redis.flushdb()
            await redis.aclose()

    return _project


IN_PROGRESS = {"id": "proj-abc12", "title": "Fix bug", "status": "in_progress"}
UNRELATED = {"id": "proj-other", "title": "Unrelated", "status": "open"}


@pytest.mark.asyncio
async def test_claim_by_short_id_stores_full_id(project):
    async with project() as p:
        # The bead is created in the same sync that claims it.
        await p.full_sync(p.alice, [IN_PROGRESS], "update abc12 --claim")
        assert await p.claims() == [("proj-abc12", "alice")]


@pytest.mark.asyncio
async def test_close_by_full_id_releases_claim_made_by_short_id(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS, UNRELATED], "update abc12 --claim")
        # The sync shows no status change for the closed bead, so only the
        # command line can release its claim.
        await p.incremental_sync(p.alice, [{**UNRELATED, "title": "Renamed"}], "close proj-abc12")
        assert await p.claims() == []


@pytest.mark.asyncio
async def test_close_by_short_id_releases_claim_made_by_full_id(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS, UNRELATED], "update proj-abc12 --claim")
        await p.incremental_sync(p.bob, [{**UNRELATED, "title": "Renamed"}], "close abc12")
        assert await p.claims() == []


@pytest.mark.asyncio
async def test_command_conflict_check_resolves_short_id(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update proj-abc12 --claim")

        data = await p.command(p.bob, "update abc12 --claim")
        assert data["approved"] is False
        assert data["reason"] == "proj-abc12 is being worked on by alice (Alice)"

        data = await p.command(p.alice, "update abc12 --claim")
        assert data["approved"] is True


@pytest.mark.asyncio
async def test_command_conflict_check_catches_full_id_against_short_id_claim(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update abc12 --claim")

        data = await p.command(p.bob, "update proj-abc12 --status in_progress")
        assert data["approved"] is False
        assert "alice" in data["reason"]


@pytest.mark.asyncio
async def test_sync_conflict_check_resolves_short_id(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update proj-abc12 --claim")

        data = await p.full_sync(p.bob, [IN_PROGRESS], "update abc12 --claim")
        assert data["claim_rejected"] is True
        assert data["claim_rejected_reason"] == "proj-abc12 is being worked on by alice (Alice)"
        assert await p.claims() == [("proj-abc12", "alice")]


@pytest.mark.asyncio
async def test_ambiguous_or_unknown_id_creates_no_claim(project):
    async with project() as p:
        beads = [
            {"id": "proj-ab1", "title": "One", "status": "in_progress"},
            {"id": "proj-ab2", "title": "Two", "status": "in_progress"},
        ]
        with resolver_warnings() as warnings:
            await p.full_sync(p.alice, beads, "update ab --claim")
            await p.full_sync(p.alice, beads, "update zzz9 --claim")
        assert await p.claims() == []
        assert len(warnings) == 2
        assert "ab" in warnings[0] and "ambiguous" in warnings[0]
        assert "zzz9" in warnings[1] and "no bead" in warnings[1]


@pytest.mark.asyncio
async def test_ambiguous_id_releases_nothing(project):
    async with project() as p:
        beads = [
            {"id": "proj-ab1", "title": "One", "status": "in_progress"},
            {"id": "proj-ab2", "title": "Two", "status": "open"},
            UNRELATED,
        ]
        await p.full_sync(p.alice, beads, "update proj-ab1 --claim")
        with resolver_warnings() as warnings:
            await p.incremental_sync(p.alice, [{**UNRELATED, "title": "Renamed"}], "close ab")
        assert await p.claims() == [("proj-ab1", "alice")]
        assert len(warnings) == 1


@pytest.mark.asyncio
async def test_multi_id_update_and_close(project):
    async with project() as p:
        beads = [
            IN_PROGRESS,
            {"id": "proj-def34", "title": "Other bug", "status": "in_progress"},
            UNRELATED,
        ]
        await p.full_sync(p.alice, beads, "update abc12 proj-def34 --claim")
        assert await p.claims() == [("proj-abc12", "alice"), ("proj-def34", "alice")]

        # bdh joins bd's arguments with spaces, so the quoted reason arrives as
        # separate words; they are not ids.
        await p.incremental_sync(
            p.alice, [{**UNRELATED, "title": "Renamed"}], "close abc12 def34 --reason done other"
        )
        assert await p.claims() == []


@pytest.mark.asyncio
async def test_multi_id_claim_reports_each_conflict(project):
    async with project() as p:
        beads = [
            IN_PROGRESS,
            {"id": "proj-def34", "title": "Other bug", "status": "in_progress"},
        ]
        await p.full_sync(p.alice, beads, "update abc12 def34 --claim")

        data = await p.command(p.bob, "update abc12 def34 --claim")
        assert data["approved"] is False
        assert data["reason"] == (
            "proj-abc12 is being worked on by alice (Alice); "
            "proj-def34 is being worked on by alice (Alice)"
        )

        data = await p.full_sync(p.bob, beads, "update abc12 def34 --claim")
        assert data["claim_rejected"] is True
        assert data["claim_rejected_reason"] == (
            "proj-abc12 is being worked on by alice (Alice); "
            "proj-def34 is being worked on by alice (Alice)"
        )


@pytest.mark.asyncio
async def test_synced_close_without_command_line_releases_claim(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update proj-abc12 --claim")
        await p.incremental_sync(p.bob, [{**IN_PROGRESS, "status": "closed"}], None)
        assert await p.claims() == []


@pytest.mark.asyncio
async def test_synced_return_to_open_releases_claim(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update proj-abc12 --claim")
        await p.incremental_sync(p.bob, [{**IN_PROGRESS, "status": "open"}], "sync")
        assert await p.claims() == []


@pytest.mark.asyncio
async def test_synced_change_that_stays_in_progress_keeps_claim(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS], "update proj-abc12 --claim")
        await p.incremental_sync(p.bob, [{**IN_PROGRESS, "title": "Renamed"}], None)
        assert await p.claims() == [("proj-abc12", "alice")]


@pytest.mark.asyncio
async def test_delete_by_short_id_releases_claim_without_warning(project):
    async with project() as p:
        await p.full_sync(p.alice, [IN_PROGRESS, UNRELATED], "update abc12 --claim")
        with resolver_warnings() as warnings:
            await p.incremental_sync(p.alice, [], "delete abc12 --force", ["proj-abc12"])
        assert await p.claims() == []
        assert warnings == []
