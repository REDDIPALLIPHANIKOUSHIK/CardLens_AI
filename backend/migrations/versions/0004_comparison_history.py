"""Persist account-owned card comparisons."""
from alembic import op
import sqlalchemy as sa

revision = "0004_comparison_history"
down_revision = "0003_user_favorites"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    if "comparison_history" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "comparison_history",
            sa.Column("id",sa.String(length=36),primary_key=True),
            sa.Column("user_id",sa.String(length=36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
            sa.Column("profile_snapshot",sa.JSON(),nullable=False),
            sa.Column("card_ids",sa.JSON(),nullable=False),
            sa.Column("results",sa.JSON(),nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        )
    indexes={index["name"] for index in sa.inspect(bind).get_indexes("comparison_history")}
    if "ix_comparison_history_user_id" not in indexes:
        op.create_index("ix_comparison_history_user_id","comparison_history",["user_id"])

def downgrade():
    op.drop_index("ix_comparison_history_user_id",table_name="comparison_history")
    op.drop_table("comparison_history")
