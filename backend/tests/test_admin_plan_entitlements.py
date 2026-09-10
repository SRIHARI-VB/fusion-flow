"""Offline unit tests for `modules/admin/service.py::is_feature_enabled`'s
new plan tier.

No Postgres needed: a tiny fake `AsyncSession` returns pre-queued results in
the exact call order `is_feature_enabled` issues them in, so these tests
exercise the resolution-order *logic* without touching a real database.

`Business.plan_id` does not exist on the ORM model in this checkout yet
(see this task's report) - `is_feature_enabled` reads it via
`getattr(business, "plan_id", None)`, so a plain `SimpleNamespace(plan_id=...)`
stands in for "a Business row once that column exists" below; that's exactly
the duck-typed access pattern the real code uses.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.admin.models import FeatureFlag, FeatureFlagOverride, PlanFeatureFlag

_TENANT_ID = uuid.uuid4()
_FLAG_ID = uuid.uuid4()
_PLAN_ID = uuid.uuid4()


def _flag(*, is_global_default: bool) -> FeatureFlag:
    return FeatureFlag(id=_FLAG_ID, key="support_agent_enabled", is_global_default=is_global_default)


class _Result:
    """Stands in for whatever `session.execute(...)` returns: supports both
    `.scalar_one_or_none()` and `.scalars().all()`, whichever the caller uses."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeSession:
    """Returns queued `execute()` results in call order; `get()` is fixed.

    Deliberately asserts-by-construction: if the function under test issues
    more `execute()` calls than queued (e.g. a resolution step ran that
    should have short-circuited), popping from the empty list raises
    `IndexError`, failing the test loudly.
    """

    def __init__(self, execute_results: list, get_result=None):
        self._execute_results = list(execute_results)
        self._get_result = get_result

    async def execute(self, *_args, **_kwargs):
        return _Result(self._execute_results.pop(0))

    async def get(self, *_args, **_kwargs):
        return self._get_result


async def test_unknown_flag_resolves_false_without_any_further_query() -> None:
    session = _FakeSession(execute_results=[None])
    assert await admin_service.is_feature_enabled(session, "does-not-exist", _TENANT_ID) is False
    assert session._execute_results == []


async def test_tenant_override_wins_over_everything_else() -> None:
    flag = _flag(is_global_default=False)
    tenant_override = FeatureFlagOverride(id=uuid.uuid4(), feature_flag_id=_FLAG_ID, tenant_id=_TENANT_ID, enabled=True)
    session = _FakeSession(execute_results=[flag, tenant_override])
    assert await admin_service.is_feature_enabled(session, flag.key, _TENANT_ID) is True
    # Short-circuited before ever reaching the plan/global-override queries.
    assert session._execute_results == []


async def test_plan_entitlement_enables_a_flag_that_defaults_off() -> None:
    flag = _flag(is_global_default=False)
    business = SimpleNamespace(plan_id=_PLAN_ID)
    plan_flag = PlanFeatureFlag(id=uuid.uuid4(), plan_id=_PLAN_ID, feature_flag_id=_FLAG_ID, enabled=True)
    session = _FakeSession(
        execute_results=[flag, None, plan_flag],  # flag, tenant_override(None), plan_flag
        get_result=business,
    )
    assert await admin_service.is_feature_enabled(session, flag.key, _TENANT_ID) is True
    assert session._execute_results == []


async def test_plan_entitlement_disables_a_flag_that_defaults_on() -> None:
    flag = _flag(is_global_default=True)
    business = SimpleNamespace(plan_id=_PLAN_ID)
    plan_flag = PlanFeatureFlag(id=uuid.uuid4(), plan_id=_PLAN_ID, feature_flag_id=_FLAG_ID, enabled=False)
    session = _FakeSession(execute_results=[flag, None, plan_flag], get_result=business)
    assert await admin_service.is_feature_enabled(session, flag.key, _TENANT_ID) is False


async def test_no_plan_falls_through_to_global_override() -> None:
    """`Business.plan_id` unset (or the tenant has no plan) - unchanged
    pre-plan-tier behavior: tenant override > global override > default."""
    flag = _flag(is_global_default=False)
    business = SimpleNamespace(plan_id=None)
    global_override = FeatureFlagOverride(id=uuid.uuid4(), feature_flag_id=_FLAG_ID, tenant_id=None, enabled=True)
    session = _FakeSession(
        execute_results=[flag, None, global_override],  # flag, tenant_override(None), global_override
        get_result=business,
    )
    assert await admin_service.is_feature_enabled(session, flag.key, _TENANT_ID) is True


async def test_business_missing_plan_id_attribute_entirely_is_safe() -> None:
    """Forward-compat guard: before the `Business.plan_id` migration lands,
    `get(Business, ...)` returns a real ORM instance with no `plan_id`
    attribute at all - `getattr(..., None)` must not raise."""
    flag = _flag(is_global_default=True)
    business_without_plan_id = SimpleNamespace()  # no plan_id attribute
    session = _FakeSession(execute_results=[flag, None, None], get_result=business_without_plan_id)
    # flag, tenant_override(None), then falls through to global_override(None) -> default True
    assert await admin_service.is_feature_enabled(session, flag.key, _TENANT_ID) is True


async def test_no_tenant_id_skips_tenant_and_plan_resolution_entirely() -> None:
    flag = _flag(is_global_default=False)
    global_override = FeatureFlagOverride(id=uuid.uuid4(), feature_flag_id=_FLAG_ID, tenant_id=None, enabled=True)
    session = _FakeSession(execute_results=[flag, global_override])
    assert await admin_service.is_feature_enabled(session, flag.key, None) is True
    assert session._execute_results == []
