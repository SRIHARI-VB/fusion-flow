"""Offline unit tests for the approval-gated signup/login flow and the new
admin approve/deny tenant actions.

Same fake-AsyncSession-with-queued-results approach as
test_admin_plan_entitlements.py / test_connectors_access_gating.py - no
Postgres needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from fusionflow.core.security import hash_password
from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.admin.service import AdminError
from fusionflow.modules.auth import service as auth_service
from fusionflow.modules.auth.models import User
from fusionflow.modules.auth.service import AuthError, IssuedSession
from fusionflow.modules.tenancy.models import Business, BusinessStatus, Membership, MembershipRole

_PASSWORD = "correct horse battery staple"


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, execute_results: list, get_result=None, get_results: list | None = None):
        self._execute_results = list(execute_results)
        self._get_result = get_result
        # Some flows call `session.get` more than once for different rows
        # (e.g. `refresh()`: the user, then - after this fix - the
        # business) - `get_results`, when given, is popped in order instead
        # of always returning the same single `get_result`.
        self._get_results = list(get_results) if get_results is not None else None
        self.added: list[object] = []

    async def execute(self, *_args, **_kwargs):
        return _Result(self._execute_results.pop(0))

    async def get(self, *_args, **_kwargs):
        if self._get_results is not None:
            return self._get_results.pop(0)
        return self._get_result

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        return None


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash=hash_password(_PASSWORD),
        is_platform_admin=False,
    )


def _business(status: BusinessStatus, **kwargs) -> Business:
    return Business(
        id=uuid.uuid4(),
        name="Acme",
        slug=f"acme-{uuid.uuid4().hex[:8]}",
        status=status,
        **kwargs,
    )


def _membership(business: Business) -> Membership:
    return Membership(
        id=uuid.uuid4(), user_id=uuid.uuid4(), business_id=business.id, role=MembershipRole.OWNER
    )


# ---------------------------------------------------------------------------
# login() - pending / denied / suspended messaging
# ---------------------------------------------------------------------------


async def test_login_blocks_pending_business_with_clear_message(monkeypatch) -> None:
    user = _user()
    business = _business(BusinessStatus.PENDING_APPROVAL)
    session = _FakeSession(execute_results=[user])

    async def _fake_memberships(_session, _user_id):
        return [(_membership(business), business)]

    monkeypatch.setattr(auth_service.tenancy_service, "list_memberships_for_user", _fake_memberships)

    with pytest.raises(AuthError) as exc_info:
        await auth_service.login(session, email=user.email, password=_PASSWORD)
    assert exc_info.value.status_code == 403
    assert "awaiting admin approval" in exc_info.value.detail


async def test_login_blocks_denied_business_and_includes_reason(monkeypatch) -> None:
    user = _user()
    business = _business(BusinessStatus.DENIED, denial_reason="Not a fit for this platform")
    session = _FakeSession(execute_results=[user])

    async def _fake_memberships(_session, _user_id):
        return [(_membership(business), business)]

    monkeypatch.setattr(auth_service.tenancy_service, "list_memberships_for_user", _fake_memberships)

    with pytest.raises(AuthError) as exc_info:
        await auth_service.login(session, email=user.email, password=_PASSWORD)
    assert exc_info.value.status_code == 403
    assert "denied" in exc_info.value.detail.lower()
    assert "Not a fit for this platform" in exc_info.value.detail


async def test_login_blocks_suspended_business_with_clear_message(monkeypatch) -> None:
    user = _user()
    business = _business(BusinessStatus.SUSPENDED)
    session = _FakeSession(execute_results=[user])

    async def _fake_memberships(_session, _user_id):
        return [(_membership(business), business)]

    monkeypatch.setattr(auth_service.tenancy_service, "list_memberships_for_user", _fake_memberships)

    with pytest.raises(AuthError) as exc_info:
        await auth_service.login(session, email=user.email, password=_PASSWORD)
    assert exc_info.value.status_code == 403
    assert "suspended" in exc_info.value.detail.lower()


async def test_login_not_blocked_when_at_least_one_business_is_active(monkeypatch) -> None:
    """A user with one PENDING business and one ACTIVE business must still
    be able to log into the active one - only "every membership is
    inactive" triggers the new blocking branch."""
    user = _user()
    pending_business = _business(BusinessStatus.PENDING_APPROVAL)
    active_business = _business(BusinessStatus.ACTIVE)
    session = _FakeSession(execute_results=[user])

    async def _fake_memberships(_session, _user_id):
        return [
            (_membership(pending_business), pending_business),
            (_membership(active_business), active_business),
        ]

    async def _fake_revoke(*_args, **_kwargs):
        return None

    async def _fake_issue(_session, *, user, business_id, role):
        return IssuedSession(user=user, access_token="tok", refresh_token_raw="raw", expires_in=900)

    monkeypatch.setattr(auth_service.tenancy_service, "list_memberships_for_user", _fake_memberships)
    monkeypatch.setattr(auth_service, "_revoke_active_tokens_for_business", _fake_revoke)
    monkeypatch.setattr(auth_service, "_issue_for_business", _fake_issue)

    issued = await auth_service.login(session, email=user.email, password=_PASSWORD)
    assert issued.user is user


# ---------------------------------------------------------------------------
# refresh() - tenant-scoped session must keep returning its business
# ---------------------------------------------------------------------------


async def test_refresh_of_tenant_scoped_session_still_returns_the_business(monkeypatch) -> None:
    """Regression test: refresh()'s tenant-scoped branch (row.business_id
    is not None - by far the common case, since it covers every already-
    logged-in user's session refresh) used to leave `memberships` as its
    initial empty list, so `to_token_response`'s `businesses` came back
    empty and the frontend could never match one against the token's
    `tenant_id` claim - `business` silently went `null` on every refresh."""
    from fusionflow.modules.auth.http import to_token_response
    from fusionflow.modules.auth.models import RefreshToken

    user = _user()
    user.created_at = datetime.now(timezone.utc)  # required by UserOut, not set by the _user() helper
    business = _business(BusinessStatus.ACTIVE, messaging_paused=False)
    membership = _membership(business)
    refresh_row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash="irrelevant-fake-session-ignores-the-actual-query",
        family_id=uuid.uuid4(),
        business_id=business.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        revoked_at=None,
    )
    session = _FakeSession(
        execute_results=[refresh_row],
        get_results=[user, business],
    )

    async def _fake_get_membership(_session, *, user_id, business_id):
        return membership

    monkeypatch.setattr(auth_service.tenancy_service, "get_membership", _fake_get_membership)

    issued = await auth_service.refresh(session, raw_token="whatever-raw-token")

    assert issued.requires_business_selection is False
    assert issued.memberships == [(membership, business)]

    token_response = to_token_response(issued)
    assert len(token_response.businesses) == 1
    assert token_response.businesses[0].id == business.id


# ---------------------------------------------------------------------------
# admin_service.approve_tenant / deny_tenant
# ---------------------------------------------------------------------------


async def test_approve_tenant_activates_and_clears_denial_reason() -> None:
    business = _business(BusinessStatus.PENDING_APPROVAL, denial_reason="old reason")
    session = _FakeSession(execute_results=[], get_result=business)
    admin_id = uuid.uuid4()

    result = await admin_service.approve_tenant(session, business.id, admin_id=admin_id)

    assert result.status == BusinessStatus.ACTIVE
    assert result.denial_reason is None
    assert result.reviewed_by == admin_id
    assert result.reviewed_at is not None


async def test_approve_tenant_rejects_non_pending_business() -> None:
    business = _business(BusinessStatus.ACTIVE)
    session = _FakeSession(execute_results=[], get_result=business)

    with pytest.raises(AdminError) as exc_info:
        await admin_service.approve_tenant(session, business.id, admin_id=uuid.uuid4())
    assert exc_info.value.status_code == 409


async def test_approve_tenant_not_found() -> None:
    session = _FakeSession(execute_results=[], get_result=None)

    with pytest.raises(AdminError) as exc_info:
        await admin_service.approve_tenant(session, uuid.uuid4(), admin_id=uuid.uuid4())
    assert exc_info.value.status_code == 404


async def test_deny_tenant_sets_denied_status_and_reason() -> None:
    business = _business(BusinessStatus.PENDING_APPROVAL)
    session = _FakeSession(execute_results=[], get_result=business)

    result = await admin_service.deny_tenant(
        session, business.id, admin_id=uuid.uuid4(), reason="Missing business documentation"
    )

    assert result.status == BusinessStatus.DENIED
    assert result.denial_reason == "Missing business documentation"


async def test_deny_tenant_rejects_non_pending_business() -> None:
    business = _business(BusinessStatus.DENIED)
    session = _FakeSession(execute_results=[], get_result=business)

    with pytest.raises(AdminError) as exc_info:
        await admin_service.deny_tenant(session, business.id, admin_id=uuid.uuid4(), reason=None)
    assert exc_info.value.status_code == 409
