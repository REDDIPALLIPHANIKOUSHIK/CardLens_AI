"""Store account-level language preferences."""
from alembic import op
import sqlalchemy as sa

revision = "0005_user_settings"
down_revision = "0004_comparison_history"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    if "user_settings" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "user_settings",
            sa.Column("id",sa.String(length=36),primary_key=True),
            sa.Column("user_id",sa.String(length=36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
            sa.Column("voice_language",sa.String(length=10),nullable=False,server_default="en"),
            sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
            sa.UniqueConstraint("user_id",name="uq_user_settings_user_id"),
        )
    indexes={index["name"] for index in sa.inspect(bind).get_indexes("user_settings")}
    if "ix_user_settings_user_id" not in indexes:
        op.create_index("ix_user_settings_user_id","user_settings",["user_id"])

def downgrade():
    op.drop_index("ix_user_settings_user_id",table_name="user_settings")
    op.drop_table("user_settings")
