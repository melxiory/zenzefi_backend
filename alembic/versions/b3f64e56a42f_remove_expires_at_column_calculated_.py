"""Remove expires_at column (calculated from activated_at)

Revision ID: b3f64e56a42f
Revises: f909ad8c76ed
Create Date: 2025-10-24 12:52:41.434973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f64e56a42f'
down_revision: Union[str, Sequence[str], None] = 'f909ad8c76ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove expires_at column - now calculated as activated_at + duration_hours."""
    op.drop_column('access_tokens', 'expires_at')


def downgrade() -> None:
    """Restore expires_at column."""
    op.add_column('access_tokens',
                  sa.Column('expires_at', sa.DateTime(), nullable=True))

    # Recalculate expires_at for existing tokens
    op.execute("""
        UPDATE access_tokens
        SET expires_at = activated_at + (duration_hours || ' hours')::interval
        WHERE activated_at IS NOT NULL
    """)
