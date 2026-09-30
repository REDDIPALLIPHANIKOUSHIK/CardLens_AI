"""Add user-owned saved cards."""
from alembic import op
import sqlalchemy as sa

revision = "0003_user_favorites"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "user_favorites" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "user_favorites",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("card_id", sa.String(length=100), sa.ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "card_id", name="uq_user_favorites_user_card"),
        )
    indexes={index["name"] for index in sa.inspect(bind).get_indexes("user_favorites")}
    for name,column in (("ix_user_favorites_user_id","user_id"),("ix_user_favorites_card_id","card_id")):
        if name not in indexes:
            op.create_index(name,"user_favorites",[column])

def downgrade():
    op.drop_index("ix_user_favorites_card_id",table_name="user_favorites")
    op.drop_index("ix_user_favorites_user_id",table_name="user_favorites")
    op.drop_table("user_favorites")
