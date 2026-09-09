"""Admin-module dependency aliases.

`require_platform_admin` already exists in `fusionflow.core.deps` (Wave 0
stubbed it there, re-checking `users.is_platform_admin` from the DB rather
than trusting the JWT claim alone, exactly per the plan's Auth Flow /
super-admin paragraph). This module does not redefine it - it only adds the
`Annotated`-alias convenience `core/deps.py` uses for its own dependencies,
so `modules/admin/router.py` reads the same way the rest of the codebase
does (`CurrentUserDep`, `TenantContextDep`, ...).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from fusionflow.core.deps import SessionDep, require_platform_admin  # noqa: F401 - re-exported
from fusionflow.modules.auth.models import User

PlatformAdminDep = Annotated[User, Depends(require_platform_admin)]

__all__ = ["PlatformAdminDep", "SessionDep", "require_platform_admin"]
