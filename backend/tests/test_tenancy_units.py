"""Unit test for `modules/tenancy/service.py::list_members_of_business`.

Needs a live Postgres (via `$TEST_DATABASE_URL`) because it exercises a
real join across `memberships`/`users`/`businesses` — all platform tables
with no RLS policy, so (unlike `test_rls_isolation.py`) no tenant context
needs to be set here, but a real session is still required since the
codebase has no offline SQLAlchemy-select fake for join queries. Skips
(rather than fails) when `TEST_DATABASE_URL` is unset, same as every other
Postgres-gated test in this suite.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.core.security import hash_password
from fusionflow.modules.auth.models import User
from fusionflow.modules.tenancy import service as tenancy_service
from fusionflow.modules.tenancy.models import Business, Membership, MembershipRole
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


@pytest.fixture
async def business_with_members(pg_session_factory):
    """One business, one owner, one accepted member, one not-yet-accepted invite."""
    business_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    invitee_id = uuid.uuid4()

    async with pg_session_factory() as session:
        session.add(
            Business(
                id=business_id,
                name="Members Test Co",
                slug=f"members-test-{business_id.hex[:12]}",
            )
        )
        for uid, email in (
            (owner_id, f"owner-{owner_id.hex[:8]}@example.com"),
            (member_id, f"member-{member_id.hex[:8]}@example.com"),
            (invitee_id, f"invitee-{invitee_id.hex[:8]}@example.com"),
        ):
            session.add(User(id=uid, email=email, password_hash=hash_password("x")))
        await session.flush()

        session.add(
            Membership(
                id=uuid.uuid4(),
                user_id=owner_id,
                business_id=business_id,
                role=MembershipRole.OWNER,
                accepted_at=None,
            )
        )
        session.add(
            Membership(
                id=uuid.uuid4(),
                user_id=member_id,
                business_id=business_id,
                role=MembershipRole.MEMBER,
                accepted_at=None,
            )
        )
        session.add(
            Membership(
                id=uuid.uuid4(),
                user_id=invitee_id,
                business_id=business_id,
                role=MembershipRole.VIEWER,
                accepted_at=None,
            )
        )
        await session.commit()

    yield business_id, {owner_id: "owner", member_id: "member", invitee_id: "invitee"}

    async with pg_session_factory() as session:
        # ON DELETE CASCADE from businesses removes the membership rows;
        # users are deleted explicitly since nothing cascades from business.
        await session.delete(await session.get(Business, business_id))
        for uid in (owner_id, member_id, invitee_id):
            user = await session.get(User, uid)
            if user is not None:
                await session.delete(user)
        await session.commit()


async def test_list_members_of_business_returns_every_member_with_role_and_email(
    pg_session_factory, business_with_members
) -> None:
    business_id, users_by_id = business_with_members
    async with pg_session_factory() as session:
        results = await tenancy_service.list_members_of_business(session, business_id)

    assert len(results) == 3
    seen = {membership.user_id: (user.email, membership.role) for membership, user in results}
    assert set(seen.keys()) == set(users_by_id.keys())
    for user_id, (email, role) in seen.items():
        assert email.startswith(users_by_id[user_id])
        assert role in (MembershipRole.OWNER, MembershipRole.MEMBER, MembershipRole.VIEWER)


async def test_list_members_of_business_is_scoped_to_the_given_business(
    pg_session_factory, business_with_members
) -> None:
    """A second, unrelated business must not leak into the first's member list."""
    business_id, _ = business_with_members
    other_business_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()

    async with pg_session_factory() as session:
        session.add(
            Business(
                id=other_business_id,
                name="Other Co",
                slug=f"other-co-{other_business_id.hex[:12]}",
            )
        )
        session.add(
            User(
                id=other_owner_id,
                email=f"other-{other_owner_id.hex[:8]}@example.com",
                password_hash=hash_password("x"),
            )
        )
        await session.flush()
        session.add(
            Membership(
                id=uuid.uuid4(),
                user_id=other_owner_id,
                business_id=other_business_id,
                role=MembershipRole.OWNER,
                accepted_at=None,
            )
        )
        await session.commit()

    try:
        async with pg_session_factory() as session:
            results = await tenancy_service.list_members_of_business(session, business_id)
        assert other_owner_id not in {membership.user_id for membership, _ in results}
    finally:
        async with pg_session_factory() as session:
            await session.delete(await session.get(Business, other_business_id))
            user = await session.get(User, other_owner_id)
            if user is not None:
                await session.delete(user)
            await session.commit()
