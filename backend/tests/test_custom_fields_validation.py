"""Offline unit tests for `modules/custom_fields/validation.py`.

No Postgres needed: `FieldDefinition` instances are constructed in memory
(never flushed to a session) purely to exercise
`validate_custom_fields`/`build_custom_fields_model`.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.modules.custom_fields.models import EntityType, FieldDefinition, FieldType
from fusionflow.modules.custom_fields.validation import CustomFieldValidationError, validate_custom_fields

_TENANT_ID = uuid.uuid4()


def _definition(key: str, field_type: FieldType, *, required: bool = False, options=None) -> FieldDefinition:
    return FieldDefinition(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        entity_type=EntityType.PRODUCT,
        key=key,
        label=key,
        field_type=field_type,
        options=options,
        required=required,
        sort_order=0,
    )


def test_valid_payload_is_normalized_and_json_safe() -> None:
    definitions = [
        _definition("sku", FieldType.TEXT, required=True),
        _definition("stock_quantity", FieldType.NUMBER, required=True),
        _definition("launch_date", FieldType.DATE),
    ]
    result = validate_custom_fields(
        definitions, {"sku": "ABC-1", "stock_quantity": 5, "launch_date": "2024-01-01"}
    )
    assert result == {"sku": "ABC-1", "stock_quantity": 5.0, "launch_date": "2024-01-01"}


def test_missing_required_field_is_rejected() -> None:
    definitions = [_definition("sku", FieldType.TEXT, required=True)]
    with pytest.raises(CustomFieldValidationError) as exc_info:
        validate_custom_fields(definitions, {})
    assert exc_info.value.errors[0]["type"] == "missing"


def test_unknown_key_is_rejected() -> None:
    definitions = [_definition("sku", FieldType.TEXT, required=True)]
    with pytest.raises(CustomFieldValidationError) as exc_info:
        validate_custom_fields(definitions, {"sku": "ABC", "not_a_field": 1})
    assert exc_info.value.errors[0]["type"] == "extra_forbidden"


def test_wrong_type_is_rejected() -> None:
    definitions = [_definition("stock_quantity", FieldType.NUMBER, required=True)]
    with pytest.raises(CustomFieldValidationError):
        validate_custom_fields(definitions, {"stock_quantity": "not-a-number"})


def test_select_rejects_out_of_set_option() -> None:
    definitions = [_definition("size", FieldType.SELECT, options=["S", "M", "L"])]
    with pytest.raises(CustomFieldValidationError):
        validate_custom_fields(definitions, {"size": "XXL"})


def test_select_accepts_in_set_option() -> None:
    definitions = [_definition("size", FieldType.SELECT, options=["S", "M", "L"])]
    assert validate_custom_fields(definitions, {"size": "M"}) == {"size": "M"}


def test_multiselect_rejects_any_out_of_set_option() -> None:
    definitions = [_definition("tags", FieldType.MULTISELECT, options=["a", "b", "c"])]
    with pytest.raises(CustomFieldValidationError):
        validate_custom_fields(definitions, {"tags": ["a", "z"]})


def test_multiselect_accepts_subset_of_options() -> None:
    definitions = [_definition("tags", FieldType.MULTISELECT, options=["a", "b", "c"])]
    assert validate_custom_fields(definitions, {"tags": ["a", "c"]}) == {"tags": ["a", "c"]}


def test_optional_field_can_be_omitted() -> None:
    definitions = [_definition("notes", FieldType.RICHTEXT, required=False)]
    assert validate_custom_fields(definitions, {}) == {}


def test_empty_definitions_forbid_any_payload_keys() -> None:
    with pytest.raises(CustomFieldValidationError):
        validate_custom_fields([], {"anything": 1})
    assert validate_custom_fields([], {}) == {}
