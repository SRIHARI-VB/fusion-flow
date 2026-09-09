"""Single import point for every ORM model.

SQLAlchemy resolves string-based relationship targets (e.g. `Membership.user
-> "User"`) against its class registry, so *all* mapped classes must be
imported before the first mapper configuration. Importing this one module
guarantees that. Alembic's `env.py` also imports it so autogenerate sees the
full metadata, and `main.py` imports it at startup.

Later waves: add each new module's models here as they are created.
"""

from fusionflow.db.base import Base
from fusionflow.modules.auth.models import RefreshToken, User
from fusionflow.modules.tenancy.models import (
    Business,
    BusinessStatus,
    Membership,
    MembershipRole,
)

__all__ = [
    "Base",
    "Business",
    "BusinessStatus",
    "Membership",
    "MembershipRole",
    "RefreshToken",
    "User",
]
