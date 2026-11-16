"""The migration chain must apply cleanly, reverse cleanly, and match the models."""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.db.session import get_engine

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

IDENTITY_TABLES = {
    "institutions", "users", "roles", "permissions", "role_permissions", "user_roles",
    "student_profiles", "refresh_tokens", "verification_tokens", "password_reset_tokens", "audit_logs",
    "faculties", "departments", "programs", "courses", "program_courses", "resource_categories", "tags",
    "stored_files", "resources", "resource_versions", "resource_tags", "course_resources",
    "resource_reviews", "entitlements", "bookmarks", "resource_downloads",
    "print_shops", "print_shop_staff", "print_pricing_rules", "print_documents", "print_orders",
    "print_order_items", "order_status_history", "payments", "payment_transactions", "payment_events", "refunds",
}  # fmt: skip


def test_upgrade_downgrade_upgrade_and_models_match() -> None:
    config = Config(str(ALEMBIC_INI))

    command.upgrade(config, "head")
    assert IDENTITY_TABLES <= set(inspect(get_engine()).get_table_names())

    command.downgrade(config, "base")
    assert not (IDENTITY_TABLES & set(inspect(get_engine()).get_table_names()))

    command.upgrade(config, "head")
    assert IDENTITY_TABLES <= set(inspect(get_engine()).get_table_names())
    command.check(config)  # raises if the models and the migrated schema disagree


def test_there_is_a_single_migration_head() -> None:
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_heads()
    assert len(heads) == 1
