"""Static module-dependency metadata for the FEATURE catalog.

`MODULE_DEPENDENCIES[key]` lists the modules `key` needs in order to
function fully (e.g. the Orders page picks a customer from `/customers`,
so revoking/restricting `customers` degrades `orders`). It is advisory
metadata surfaced to the UI/admin ("X also needs Y") - it never gates
access by itself; `require_module_access` still checks each module on its
own.
"""

from __future__ import annotations

MODULE_DEPENDENCIES: dict[str, list[str]] = {
    "orders": ["customers", "products"],
    "payments": ["orders", "customers"],
    "tickets": ["customers"],
    "appointments": ["customers"],
    "clinic_queue": ["customers"],
    "workflows": [],
    "customers": [],
    "products": [],
    "services": [],
    "coupons": [],
    "offers": [],
    "kb": [],
    "custom_fields": [],
    "communication": [],
    "inbox": [],
}


def dependents_of(key: str) -> list[str]:
    """Modules that list `key` as a dependency (sorted, stable)."""
    return sorted(k for k, deps in MODULE_DEPENDENCIES.items() if key in deps)
