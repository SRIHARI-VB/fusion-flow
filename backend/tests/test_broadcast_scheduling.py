"""Tests for recurring/scheduled bulk-messaging support:

* `models.compute_next_run_at` — pure, offline, no DB (every frequency,
  including month-end clamping and timezone correctness).
* `broadcast.scheduled_send`'s registration/output_schema, and the new
  `applicable_purposes` metadata field's presence on the five automation
  triggers + this new broadcast trigger (offline - direct registry reads).
* The `purpose` filter inside `service.list_node_types_with_templates`,
  exercised offline with `admin_service`/`connector_service` monkeypatched
  the same way `test_module_access_gating.py` already does for entitlement
  filtering - no DB needed since every dependency of the function under
  test is stubbed.
* Schedule CRUD (`service.create_schedule`/`list_schedules`/
  `update_schedule`/`delete_schedule`) and `engine.schedule_poller.poll_once`
  firing a due schedule and skipping a non-due one - `requires_postgres`
  (real `businesses`/`workflows`/RLS needed), same convention as
  `test_workflow_delete.py`. Skips without `$TEST_DATABASE_URL`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.registry import node_executor_registry, trigger_registry
from fusionflow.modules.workflows.models import compute_next_run_at
from fusionflow.modules.workflows.nodes.broadcast_scheduled_send import (
    NODE_TYPE as BROADCAST_SCHEDULED_SEND,
)
from tests.conftest import requires_postgres

UTC = timezone.utc


# ---------------------------------------------------------------------------
# compute_next_run_at - pure, offline
# ---------------------------------------------------------------------------


def test_compute_next_run_at_once_returns_run_at_unchanged() -> None:
    run_at = datetime(2026, 12, 25, 9, 0, tzinfo=UTC)
    result = compute_next_run_at(
        "once", None, None, None, "UTC", after=datetime(2026, 1, 1, tzinfo=UTC), run_at=run_at
    )
    assert result == run_at


def test_compute_next_run_at_once_requires_run_at() -> None:
    with pytest.raises(ValueError):
        compute_next_run_at("once", None, None, None, "UTC", after=datetime(2026, 1, 1, tzinfo=UTC))


def test_compute_next_run_at_daily_rolls_to_tomorrow_if_time_passed() -> None:
    after = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
    result = compute_next_run_at("daily", "09:00", None, None, "UTC", after=after)
    assert result == datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def test_compute_next_run_at_daily_stays_today_if_time_not_yet_passed() -> None:
    after = datetime(2026, 9, 16, 8, 0, tzinfo=UTC)
    result = compute_next_run_at("daily", "09:00", None, None, "UTC", after=after)
    assert result == datetime(2026, 9, 16, 9, 0, tzinfo=UTC)


def test_compute_next_run_at_weekly_finds_next_matching_weekday() -> None:
    # 2026-09-16 is a Wednesday (weekday()==2).
    after = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
    # Friday (weekday()==4) at 09:00, two days later.
    result = compute_next_run_at("weekly", "09:00", [4], None, "UTC", after=after)
    assert result == datetime(2026, 9, 18, 9, 0, tzinfo=UTC)


def test_compute_next_run_at_weekly_rolls_to_next_week_if_only_match_already_passed() -> None:
    # Wednesday itself, but 09:00 has already passed today - next match is
    # next Wednesday, not later this week.
    after = datetime(2026, 9, 16, 10, 0, tzinfo=UTC)
    result = compute_next_run_at("weekly", "09:00", [2], None, "UTC", after=after)
    assert result == datetime(2026, 9, 23, 9, 0, tzinfo=UTC)


def test_compute_next_run_at_weekly_requires_weekdays() -> None:
    with pytest.raises(ValueError):
        compute_next_run_at("weekly", "09:00", None, None, "UTC", after=datetime(2026, 1, 1, tzinfo=UTC))


def test_compute_next_run_at_monthly_clamps_to_last_day_of_shorter_month() -> None:
    # April has 30 days - day_of_month=31 clamps to April 30.
    after = datetime(2026, 4, 15, 8, 0, tzinfo=UTC)
    result = compute_next_run_at("monthly", "10:00", None, 31, "UTC", after=after)
    assert result == datetime(2026, 4, 30, 10, 0, tzinfo=UTC)


def test_compute_next_run_at_monthly_rolls_to_next_month_when_this_months_candidate_passed() -> None:
    # This month's (clamped) candidate has already passed - rolls to next
    # month, re-clamped for that month's own length.
    after = datetime(2026, 4, 30, 11, 0, tzinfo=UTC)
    result = compute_next_run_at("monthly", "10:00", None, 31, "UTC", after=after)
    assert result == datetime(2026, 5, 31, 10, 0, tzinfo=UTC)


def test_compute_next_run_at_monthly_requires_day_of_month() -> None:
    with pytest.raises(ValueError):
        compute_next_run_at("monthly", "10:00", None, None, "UTC", after=datetime(2026, 1, 1, tzinfo=UTC))


def test_compute_next_run_at_unknown_frequency_raises() -> None:
    with pytest.raises(ValueError):
        compute_next_run_at("yearly", "10:00", None, None, "UTC", after=datetime(2026, 1, 1, tzinfo=UTC))


def test_compute_next_run_at_requires_timezone_aware_after() -> None:
    with pytest.raises(ValueError):
        compute_next_run_at("daily", "09:00", None, None, "UTC", after=datetime(2026, 1, 1))


def test_compute_next_run_at_respects_non_utc_timezone() -> None:
    # Asia/Kolkata is UTC+5:30 (no DST). 2026-09-16T03:00:00Z is
    # 2026-09-16T08:30 local - "09:00" local hasn't happened yet today, so
    # the next fire is today at 09:00 IST == 03:30 UTC.
    after = datetime(2026, 9, 16, 3, 0, tzinfo=UTC)
    result = compute_next_run_at("daily", "09:00", None, None, "Asia/Kolkata", after=after)
    assert result == datetime(2026, 9, 16, 3, 30, tzinfo=UTC)
    # Sanity-check against ZoneInfo directly.
    assert result.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%H:%M") == "09:00"


# ---------------------------------------------------------------------------
# broadcast.scheduled_send registration + output_schema (offline)
# ---------------------------------------------------------------------------


def test_broadcast_scheduled_send_registered_in_both_registries() -> None:
    assert node_executor_registry.get(BROADCAST_SCHEDULED_SEND) is not None
    assert trigger_registry.get(BROADCAST_SCHEDULED_SEND) is not None


def test_broadcast_scheduled_send_output_schema_declares_recipients() -> None:
    definition = trigger_registry.get(BROADCAST_SCHEDULED_SEND)
    assert definition is not None
    assert definition.output_schema == {
        "type": "object",
        "properties": {"recipients": {"type": "array", "items": {"type": "string"}}},
    }


def test_broadcast_scheduled_send_is_tagged_broadcast_purpose() -> None:
    definition = trigger_registry.get(BROADCAST_SCHEDULED_SEND)
    assert definition is not None
    assert definition.applicable_purposes == ["broadcast"]
    meta = definition.meta()
    assert meta.applicable_purposes == ["broadcast"]


@pytest.mark.parametrize(
    "trigger_type",
    [
        "whatsapp.message_received",
        "whatsapp.interactive_reply_received",
        "whatsapp.message_status_updated",
        "order.created",
        "payment.captured",
    ],
)
def test_domain_event_triggers_are_tagged_automation_purpose(trigger_type: str) -> None:
    definition = trigger_registry.get(trigger_type)
    assert definition is not None
    assert definition.applicable_purposes == ["automation"]


def test_manual_test_trigger_has_no_purpose_restriction() -> None:
    definition = trigger_registry.get("manual.test_trigger")
    assert definition is not None
    assert definition.applicable_purposes is None


#: Non-trigger node types explicitly tagged `["automation"]` in the
#: catalog-purpose redesign - the 6 suspend nodes (can't run inside a
#: broadcast's `flow.loop`, per the validator's "no suspend in container"
#: rule) plus 5 more tied to a single active conversation (order/ticket/
#: payment-link creation, mark-as-read).
_AUTOMATION_ONLY_NON_TRIGGER_NODE_TYPES = {
    "whatsapp.ask_question",
    "whatsapp.ask_choice",
    "whatsapp.collect_text",
    "whatsapp.ask_via_template",
    "whatsapp.ask_for_cart",
    "flow.confirm",
    "orders.create_from_cart",
    "orders.create_from_conversation",
    "create_ticket",
    "payments.send_razorpay_link",
    "whatsapp.mark_as_read",
}

#: Explicitly tagged "both" - generic reads/writes and identity resolution
#: that are legitimate inside a broadcast's loop too, not just automation.
_BOTH_PURPOSES_NON_TRIGGER_NODE_TYPES = {
    "records.query",
    "records.upsert",
    "whatsapp.find_or_create_customer",
}


def test_non_trigger_node_types_are_purpose_tagged_per_the_catalog_redesign() -> None:
    """Per the catalog-purpose redesign: the specific non-trigger node
    types above carry an explicit `applicable_purposes`; every other
    action/condition/flow-control node type stays `None` (purpose-agnostic
    infrastructure - `flow.loop`, `http.request`, `connector.action`,
    etc.)."""
    for executor in node_executor_registry.all():
        if executor.kind == "trigger":
            continue
        applicable_purposes = executor.meta().applicable_purposes
        if executor.node_type in _AUTOMATION_ONLY_NON_TRIGGER_NODE_TYPES:
            assert applicable_purposes == ["automation"], executor.node_type
        elif executor.node_type in _BOTH_PURPOSES_NON_TRIGGER_NODE_TYPES:
            assert applicable_purposes == ["automation", "broadcast"], executor.node_type
        else:
            assert applicable_purposes is None, executor.node_type


# ---------------------------------------------------------------------------
# service._matches_purpose + list_node_types_with_templates purpose filter
# (offline - admin_service/connector_service fully stubbed, no DB touched)
# ---------------------------------------------------------------------------


def test_matches_purpose_none_applicable_purposes_always_matches() -> None:
    assert workflows_service._matches_purpose(None, "automation") is True
    assert workflows_service._matches_purpose(None, "broadcast") is True
    assert workflows_service._matches_purpose(None, None) is True


def test_matches_purpose_no_purpose_requested_matches_everything() -> None:
    assert workflows_service._matches_purpose(["automation"], None) is True
    assert workflows_service._matches_purpose(["broadcast"], None) is True


def test_matches_purpose_excludes_non_matching_tag() -> None:
    assert workflows_service._matches_purpose(["automation"], "broadcast") is False
    assert workflows_service._matches_purpose(["broadcast"], "automation") is False
    assert workflows_service._matches_purpose(["automation"], "automation") is True


class _FakeSession:
    """Never actually queried - every function that would touch the DB is
    monkeypatched below, mirroring `test_module_access_gating.py`'s
    offline-entitlement-filtering test style."""


@pytest.fixture
def _stub_palette_dependencies(monkeypatch: pytest.MonkeyPatch):
    """Stubs every DB-touching dependency of `list_node_types_with_templates`
    so it can run fully offline: no `WorkflowNodeTemplate` rows, no feature
    connector types on the tenant's catalog (so the three
    `required_connector_type_key in {"whatsapp","orders","payments"}`
    triggers still need a per-key lookup - stubbed to always report
    'granted', so entitlement never interferes with the purpose-filter
    assertions below)."""
    from fusionflow.modules.admin import service as admin_service
    from fusionflow.modules.connectors import service as connector_service

    async def _fake_list_templates(session: Any, *, active_only: bool = False) -> list[Any]:
        return []

    async def _fake_list_connector_types(session: Any) -> list[Any]:
        return []

    async def _fake_get_connector_type_by_key(session: Any, type_key: str) -> Any:
        return SimpleNamespace(id=type_key, key=type_key)

    async def _fake_access_map(session: Any, *, tenant_id: Any, connector_type_ids: list[Any]) -> dict[Any, str]:
        return {cid: "granted" for cid in connector_type_ids}

    async def _fake_list_instances(session: Any, tenant_id: Any) -> list[Any]:
        return []

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", _fake_list_templates)
    monkeypatch.setattr(connector_service, "list_connector_types", _fake_list_connector_types)
    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_get_connector_type_by_key)
    monkeypatch.setattr(connector_service, "get_connector_access_map", _fake_access_map)
    monkeypatch.setattr(connector_service, "list_instances", _fake_list_instances)


async def test_node_types_broadcast_purpose_excludes_automation_only_triggers(
    _stub_palette_dependencies: None,
) -> None:
    entries = await workflows_service.list_node_types_with_templates(
        _FakeSession(), tenant_id=uuid.uuid4(), purpose="broadcast"
    )
    node_types = {e.node_type for e in entries}

    assert BROADCAST_SCHEDULED_SEND in node_types
    assert "manual.test_trigger" in node_types  # always included
    assert "whatsapp.message_received" not in node_types
    assert "order.created" not in node_types
    assert "payment.captured" not in node_types
    # Non-trigger node types are never filtered by purpose.
    assert "log.noop" in node_types


async def test_node_types_automation_purpose_excludes_broadcast_only_trigger(
    _stub_palette_dependencies: None,
) -> None:
    entries = await workflows_service.list_node_types_with_templates(
        _FakeSession(), tenant_id=uuid.uuid4(), purpose="automation"
    )
    node_types = {e.node_type for e in entries}

    assert BROADCAST_SCHEDULED_SEND not in node_types
    assert "manual.test_trigger" in node_types
    assert "whatsapp.message_received" in node_types
    assert "order.created" in node_types
    assert "payment.captured" in node_types


async def test_node_types_no_purpose_requested_includes_every_trigger(
    _stub_palette_dependencies: None,
) -> None:
    entries = await workflows_service.list_node_types_with_templates(_FakeSession(), tenant_id=uuid.uuid4())
    node_types = {e.node_type for e in entries}

    assert BROADCAST_SCHEDULED_SEND in node_types
    assert "whatsapp.message_received" in node_types
    assert "order.created" in node_types
    assert "payment.captured" in node_types


# ---------------------------------------------------------------------------
# requires_postgres: schedule CRUD + poller
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_businesses(pg_session_factory):
    from sqlalchemy import text

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    async with pg_session_factory() as session:
        for tenant_id, name in ((tenant_a, "Schedule Test Tenant A"), (tenant_b, "Schedule Test Tenant B")):
            await session.execute(
                text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                {"id": tenant_id, "name": name, "slug": f"schedule-test-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]})
        await session.commit()


def _static_schedule_payload(**overrides: Any):
    from fusionflow.modules.workflows.schemas import StaticRecipientSource, WorkflowScheduleCreateRequest

    defaults: dict[str, Any] = dict(
        frequency="daily",
        time_of_day="09:00",
        timezone="UTC",
        recipient_source=StaticRecipientSource(phone_numbers=["+15551234567"]),
    )
    defaults.update(overrides)
    return WorkflowScheduleCreateRequest(**defaults)


@requires_postgres
async def test_create_list_update_delete_schedule(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow(
            session,
            tenant_id=tenant_a,
            name="Broadcast workflow",
            graph={"nodes": [], "edges": []},
            created_by=uuid.uuid4(),
            purpose="broadcast",
        )
        await session.commit()

        await set_tenant_context(session, tenant_a)
        schedule = await workflows_service.create_schedule(
            session, tenant_id=tenant_a, workflow_id=workflow.id, payload=_static_schedule_payload()
        )
        await session.commit()
        schedule_id = schedule.id
        assert schedule.next_run_at is not None
        assert schedule.is_active is True

        await set_tenant_context(session, tenant_a)
        schedules = await workflows_service.list_schedules(session, workflow_id=workflow.id)
        assert [s.id for s in schedules] == [schedule_id]

        await set_tenant_context(session, tenant_a)
        fetched = await workflows_service.get_schedule(session, schedule_id)
        assert fetched is not None
        from fusionflow.modules.workflows.schemas import WorkflowScheduleUpdateRequest

        updated = await workflows_service.update_schedule(
            session, fetched, payload=WorkflowScheduleUpdateRequest(is_active=False)
        )
        await session.commit()
        assert updated.is_active is False

        await set_tenant_context(session, tenant_a)
        still_there = await workflows_service.get_schedule(session, schedule_id)
        assert still_there is not None
        await workflows_service.delete_schedule(session, still_there)
        await session.commit()

        await set_tenant_context(session, tenant_a)
        assert await workflows_service.get_schedule(session, schedule_id) is None


@requires_postgres
async def test_schedule_is_tenant_isolated(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context

    tenant_a, tenant_b = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow(
            session,
            tenant_id=tenant_a,
            name="Tenant A's broadcast workflow",
            graph={"nodes": [], "edges": []},
            created_by=uuid.uuid4(),
            purpose="broadcast",
        )
        schedule = await workflows_service.create_schedule(
            session, tenant_id=tenant_a, workflow_id=workflow.id, payload=_static_schedule_payload()
        )
        await session.commit()
        schedule_id = schedule.id

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_b)
        # RLS scopes the row to tenant_a - tenant_b's session can't see it.
        assert await workflows_service.get_schedule(session, schedule_id) is None


@requires_postgres
async def test_poll_once_fires_due_schedule_and_skips_non_due_one(
    pg_session_factory, two_businesses, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows.engine import schedule_poller
    from fusionflow.modules.workflows.models import WorkflowVersion

    tenant_a, _ = two_businesses

    captured_payloads: list[dict[str, Any]] = []

    async def _fake_execute_run(session, run, graph, *, trigger_payload=None):
        captured_payloads.append(trigger_payload)
        run.status = schedule_poller.RunStatus.COMPLETED
        run.completed_at = schedule_poller._now()
        return run

    monkeypatch.setattr(schedule_poller, "execute_run", _fake_execute_run)

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow(
            session,
            tenant_id=tenant_a,
            name="Pollable broadcast workflow",
            graph={"nodes": [], "edges": []},
            created_by=uuid.uuid4(),
            purpose="broadcast",
        )
        version = await workflows_service.get_latest_version(session, workflow.id)
        assert version is not None
        # Bypass full publish/validation - directly mark this version as
        # the workflow's published one with a trivially-compiled graph, the
        # only two things `_fire_schedule` actually reads.
        version.compiled_graph = {
            "nodes": [{"id": "t", "type": BROADCAST_SCHEDULED_SEND, "data": {"nodeType": BROADCAST_SCHEDULED_SEND, "config": {}}}],
            "edges": [],
        }
        workflow.current_published_version_id = version.id
        await session.commit()

        await set_tenant_context(session, tenant_a)
        due_schedule = await workflows_service.create_schedule(
            session, tenant_id=tenant_a, workflow_id=workflow.id, payload=_static_schedule_payload()
        )
        # Force it due right now (the payload's own computed next_run_at is
        # tomorrow at 09:00 UTC).
        due_schedule.next_run_at = schedule_poller._now() - timedelta(minutes=1)
        not_due_schedule = await workflows_service.create_schedule(
            session,
            tenant_id=tenant_a,
            workflow_id=workflow.id,
            payload=_static_schedule_payload(),
        )
        not_due_schedule.next_run_at = schedule_poller._now() + timedelta(days=1)
        await session.commit()
        due_id, not_due_id = due_schedule.id, not_due_schedule.id

    fired = await schedule_poller.poll_once(pg_session_factory)
    assert fired == 1
    assert captured_payloads == [{"recipients": ["+15551234567"]}]

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        fired_schedule = await workflows_service.get_schedule(session, due_id)
        assert fired_schedule is not None
        assert fired_schedule.last_run_status == "started"
        assert fired_schedule.last_run_at is not None
        # frequency="daily" - stays active, next_run_at recomputed forward.
        assert fired_schedule.is_active is True
        assert fired_schedule.next_run_at > schedule_poller._now()

        untouched_schedule = await workflows_service.get_schedule(session, not_due_id)
        assert untouched_schedule is not None
        assert untouched_schedule.last_run_at is None
        assert untouched_schedule.last_run_status is None
