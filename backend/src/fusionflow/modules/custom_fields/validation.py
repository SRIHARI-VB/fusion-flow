"""Runtime validation of `custom_fields` JSONB payloads against `field_definitions`.

Reused by every catalog write path (products, services, coupons, offers -
see `modules/catalog/service.py::validate_entity_custom_fields`) so a
`custom_fields` payload can never be persisted without matching the
tenant's own field schema for that entity_type. Not a DB constraint (JSONB
has none): this is the entire enforcement mechanism, per the plan's
explicit tradeoff ("JSONB custom fields have no DB-level referential
integrity - validated only at the application layer at write time").
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, field_validator

from fusionflow.modules.custom_fields.models import FieldDefinition, FieldType


class CustomFieldValidationError(ValueError):
    """Raised when a `custom_fields` payload does not match `field_definitions`.

    `errors` mirrors pydantic's `ValidationError.errors()` shape, so callers
    can pass it straight through as an API error response body.
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__(f"custom_fields validation failed: {errors}")


# Maps our field_type vocabulary onto the Python/pydantic type each one is
# validated and coerced as. `select` stays `str` (a single choice) while
# `multiselect` is `list` (its options constraint is enforced separately
# below, since pydantic has no built-in "one of these literal values" type
# for a *dynamically* supplied choice set).
_TYPE_MAP: dict[FieldType, Any] = {
    FieldType.TEXT: str,
    FieldType.RICHTEXT: str,
    FieldType.NUMBER: float,
    FieldType.BOOLEAN: bool,
    FieldType.DATE: dt.date,
    FieldType.SELECT: str,
    FieldType.MULTISELECT: list,
}


def _option_values(options: list[Any] | None) -> list[Any]:
    """Normalize an `options` list that may hold bare values or `{"value": ...}` dicts."""
    return [opt.get("value", opt) if isinstance(opt, dict) else opt for opt in (options or [])]


def build_custom_fields_model(definitions: Sequence[FieldDefinition]) -> type[BaseModel]:
    """Build a throwaway pydantic model mirroring one entity_type's field_definitions.

    Rebuilt on every call rather than cached: field_definitions are
    tenant-editable, and correctly invalidating a cache keyed on
    (tenant_id, entity_type) is more complexity than this buys back given
    field_definitions lists are small and this runs once per write, not in
    a hot read path.
    """
    field_specs: dict[str, Any] = {}
    option_choices: dict[str, list[Any]] = {}

    for definition in definitions:
        py_type = _TYPE_MAP.get(definition.field_type, str)
        annotation = py_type if definition.required else (py_type | None)
        default = ... if definition.required else None
        field_specs[definition.key] = (annotation, Field(default=default))

        if definition.field_type in (FieldType.SELECT, FieldType.MULTISELECT) and definition.options:
            option_choices[definition.key] = _option_values(definition.options)

    model: type[BaseModel] = create_model(
        "DynamicCustomFields",
        __config__=ConfigDict(extra="forbid"),
        **field_specs,
    )

    if option_choices:

        def _check_options(cls: type[BaseModel], value: Any, info: Any) -> Any:  # noqa: ANN401
            choices = option_choices.get(info.field_name)
            if not choices or value is None:
                return value
            candidates = value if isinstance(value, list) else [value]
            invalid = [v for v in candidates if v not in choices]
            if invalid:
                raise ValueError(f"invalid option(s) {invalid!r}; expected one of {choices!r}")
            return value

        model = create_model(
            "DynamicCustomFields",
            __base__=model,
            __validators__={
                "_check_options": field_validator(*option_choices.keys(), mode="after")(_check_options)
            },
        )

    return model


def validate_custom_fields(
    definitions: Sequence[FieldDefinition], payload: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate + normalize `payload` against `definitions`.

    Returns the normalized dict (JSON-safe: dates become ISO strings) ready
    to store in a catalog row's `custom_fields` column. Raises
    `CustomFieldValidationError` on any unknown key, missing required key,
    type mismatch, or out-of-set select/multiselect option - callers turn
    this into an HTTP 422.
    """
    model = build_custom_fields_model(definitions)
    try:
        instance = model.model_validate(payload or {})
    except ValidationError as exc:
        raise CustomFieldValidationError(exc.errors()) from exc
    return instance.model_dump(mode="json", exclude_none=True)
