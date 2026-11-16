"""Identity foundation: institutions, users, RBAC, auth tokens, audit log, reference data.

Revision ID: 0001_identity
Revises:
Create Date: 2026-10-03
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- Frozen reference-data snapshot (do not import application code into migrations) ---
INSTITUTIONS = [
    ("Makerere University", "makerere-university", "MAK"),
    ("Kyambogo University", "kyambogo-university", "KYU"),
    (
        "Mbarara University of Science and Technology",
        "mbarara-university-of-science-and-technology",
        "MUST",
    ),
    ("Uganda Christian University", "uganda-christian-university", "UCU"),
    ("Islamic University in Uganda", "islamic-university-in-uganda", "IUIU"),
]
PERMISSIONS = [
    ("user:read", "Read user accounts", False),
    ("user:update", "Update user accounts", False),
    ("user:suspend", "Suspend and reinstate user accounts", False),
    ("role:assign", "Grant and revoke roles", False),
    ("role:manage", "Manage role and permission definitions", True),
    ("institution:read", "Read institutions", False),
    ("institution:update", "Update institution details", False),
    ("institution:manage", "Create and deactivate institutions", True),
    ("resource:create", "Create resources", False),
    ("resource:update", "Update own resources", False),
    ("resource:submit", "Submit resources for review", False),
    ("resource:review", "Review and moderate resources", False),
    ("resource:publish", "Publish and archive resources", False),
    ("resource:delete", "Delete own resources", False),
    ("resource:manage_any", "Manage any resource within scope", False),
    ("order:create", "Create printing orders", False),
    ("order:read", "Read own orders", False),
    ("order:read_any", "Read any order within scope", False),
    ("order:update_status", "Update printing order status", False),
    ("payment:read", "Read payments", False),
    ("payment:manage", "Administer payments", False),
    ("advertisement:manage", "Manage advertisements and campaigns", False),
    ("analytics:read", "View analytics", False),
    ("audit:read", "Read audit logs", False),
    ("notification:read", "Read own notifications", False),
    ("settings:manage", "Manage platform settings", True),
]
ROLES = {
    "ADMIN": (
        "Administrator (platform-wide or institution-scoped)",
        [
            "advertisement:manage",
            "analytics:read",
            "audit:read",
            "institution:manage",
            "institution:read",
            "institution:update",
            "notification:read",
            "order:create",
            "order:read",
            "order:read_any",
            "order:update_status",
            "payment:manage",
            "payment:read",
            "resource:create",
            "resource:delete",
            "resource:manage_any",
            "resource:publish",
            "resource:review",
            "resource:submit",
            "resource:update",
            "role:assign",
            "role:manage",
            "settings:manage",
            "user:read",
            "user:suspend",
            "user:update",
        ],
    ),
    "PRINTING_OPERATOR": (
        "Processes printing orders for a print shop",
        ["institution:read", "notification:read", "order:read_any", "order:update_status"],
    ),
    "RESOURCE_PROVIDER": (
        "Uploads and manages academic resources",
        [
            "notification:read",
            "resource:create",
            "resource:delete",
            "resource:submit",
            "resource:update",
        ],
    ),
    "STUDENT": (
        "University student",
        ["institution:read", "notification:read", "order:create", "order:read"],
    ),
}


def _ts(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _ts_clock(name: str) -> sa.Column:
    """Event-log time: the real moment of the event (now() would be the start of the transaction)."""
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "institutions",
        _id(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("country_code", sa.String(length=2), server_default="UG", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institutions")),
        sa.UniqueConstraint("name", name=op.f("uq_institutions_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_institutions_slug")),
        sa.UniqueConstraint("code", name=op.f("uq_institutions_code")),
    )

    op.create_table(
        "users",
        _id(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sa.String(length=255), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUSPENDED')", name=op.f("ck_users_status_valid")),
    )
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "roles",
        _id(),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.true(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("name", name=op.f("uq_roles_name")),
    )

    op.create_table(
        "permissions",
        _id(),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("platform_only", sa.Boolean(), server_default=sa.false(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("code", name=op.f("uq_permissions_code")),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name=op.f("pk_role_permissions")),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    op.create_table(
        "user_roles",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], name=op.f("fk_user_roles_role_id_roles"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_user_roles_institution_id_institutions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_granted_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_institution_id", "user_roles", ["institution_id"])
    op.create_index(
        "uq_user_roles_platform_scope",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        postgresql_where=sa.text("institution_id IS NULL"),
    )
    op.create_index(
        "uq_user_roles_institution_scope",
        "user_roles",
        ["user_id", "role_id", "institution_id"],
        unique=True,
        postgresql_where=sa.text("institution_id IS NOT NULL"),
    )

    op.create_table(
        "student_profiles",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("student_number", sa.String(length=50), nullable=True),
        sa.Column("year_of_study", sa.SmallInteger(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_student_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_student_profiles_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_student_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_student_profiles_user_id")),
        sa.UniqueConstraint(
            "institution_id",
            "student_number",
            name="uq_student_profiles_institution_student_number",
        ),
        sa.CheckConstraint(
            "year_of_study IS NULL OR year_of_study BETWEEN 1 AND 8",
            name=op.f("ck_student_profiles_year_of_study_range"),
        ),
    )
    op.create_index("ix_student_profiles_institution_id", "student_profiles", ["institution_id"])

    op.create_table(
        "refresh_tokens",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=20), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
        sa.CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN "
            "('rotated', 'logout', 'reuse', 'suspended', 'password_reset')",
            name=op.f("ck_refresh_tokens_revoked_reason_valid"),
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "verification_tokens",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=20), server_default="EMAIL", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_verification_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_verification_tokens_token_hash")),
        sa.CheckConstraint(
            "purpose IN ('EMAIL', 'PHONE')", name=op.f("ck_verification_tokens_purpose_valid")
        ),
    )
    op.create_index("ix_verification_tokens_user_id", "verification_tokens", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        _id(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    op.create_table(
        "audit_logs",
        _id(),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=10), server_default="SUCCESS", nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _ts_clock("created_at"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_audit_logs_institution_id_institutions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
        sa.CheckConstraint(
            "outcome IN ('SUCCESS', 'FAILURE', 'DENIED')", name=op.f("ck_audit_logs_outcome_valid")
        ),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_institution_id", "audit_logs", ["institution_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Append-only audit log: the database itself refuses to modify or delete audit rows.
    op.execute(
        """
        CREATE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable()
        """
    )

    _seed_reference_data()


def _seed_reference_data() -> None:
    institutions = sa.table(
        "institutions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("code", sa.String()),
    )
    op.bulk_insert(
        institutions,
        [{"id": uuid.uuid4(), "name": n, "slug": s, "code": c} for n, s, c in INSTITUTIONS],
    )

    permissions = sa.table(
        "permissions",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("description", sa.String()),
        sa.column("platform_only", sa.Boolean()),
    )
    permission_ids = {code: uuid.uuid4() for code, _, _ in PERMISSIONS}
    op.bulk_insert(
        permissions,
        [
            {"id": permission_ids[code], "code": code, "description": desc, "platform_only": po}
            for code, desc, po in PERMISSIONS
        ],
    )

    roles = sa.table(
        "roles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
    )
    role_ids = {name: uuid.uuid4() for name in ROLES}
    op.bulk_insert(
        roles, [{"id": role_ids[n], "name": n, "description": d} for n, (d, _) in ROLES.items()]
    )

    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    op.bulk_insert(
        role_permissions,
        [
            {"role_id": role_ids[n], "permission_id": permission_ids[code]}
            for n, (_, codes) in ROLES.items()
            for code in codes
        ],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")
    for table in (
        "audit_logs",
        "password_reset_tokens",
        "verification_tokens",
        "refresh_tokens",
        "student_profiles",
        "user_roles",
        "role_permissions",
        "permissions",
        "roles",
        "users",
        "institutions",
    ):
        op.drop_table(table)
