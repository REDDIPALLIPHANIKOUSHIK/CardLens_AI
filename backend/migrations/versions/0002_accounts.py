"""Add email/password accounts and revocable server-side sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0002_accounts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "email" not in columns:
        op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    if "name" not in columns:
        op.add_column("users", sa.Column("name", sa.String(length=120), nullable=True))
    if "password_hash" not in columns:
        op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("users")}
    if "ix_users_email" not in index_names:
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "auth_sessions" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "auth_sessions",
            sa.Column("token_hash", sa.String(length=64), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("auth_sessions")}
    for name, column in (("ix_auth_sessions_user_id", "user_id"), ("ix_auth_sessions_expires_at", "expires_at")):
        if name not in index_names:
            op.create_index(name, "auth_sessions", [column])

def downgrade():
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "name")
    op.drop_column("users", "email")
