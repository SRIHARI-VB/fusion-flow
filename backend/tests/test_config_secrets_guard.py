"""Regression tests for the startup guard added after a security review
found `JWT_SECRET`/`ENCRYPTION_KEY` had dev-only defaults with nothing
stopping them from silently reaching a real deployment."""

from __future__ import annotations

import pytest

from fusionflow.config import (
    Settings,
    InsecureProductionConfigError,
    validate_secrets_for_environment,
)


def test_dev_default_secrets_are_fine_in_development() -> None:
    settings = Settings(ENVIRONMENT="development")
    validate_secrets_for_environment(settings)  # must not raise


def test_dev_default_jwt_secret_blocks_boot_outside_development() -> None:
    settings = Settings(ENVIRONMENT="production", ENCRYPTION_KEY="a-real-key-not-the-default")
    with pytest.raises(InsecureProductionConfigError, match="JWT_SECRET"):
        validate_secrets_for_environment(settings)


def test_dev_default_encryption_key_blocks_boot_outside_development() -> None:
    settings = Settings(ENVIRONMENT="staging", JWT_SECRET="a-real-secret-not-the-default")
    with pytest.raises(InsecureProductionConfigError, match="ENCRYPTION_KEY"):
        validate_secrets_for_environment(settings)


def test_real_secrets_boot_fine_outside_development() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        JWT_SECRET="a-real-secret-not-the-default",
        ENCRYPTION_KEY="a-real-key-not-the-default",
    )
    validate_secrets_for_environment(settings)  # must not raise
