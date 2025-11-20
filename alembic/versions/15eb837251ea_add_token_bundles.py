"""add token bundles

Revision ID: 15eb837251ea
Revises: 6ae14fae638e
Create Date: 2025-11-19 16:30:05.101707

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15eb837251ea'
down_revision: Union[str, Sequence[str], None] = '6ae14fae638e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create token_bundles table and insert default bundles."""
    from sqlalchemy.dialects import postgresql

    # Create token_bundles table
    op.create_table(
        'token_bundles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('token_count', sa.Integer, nullable=False),
        sa.Column('duration_hours', sa.Integer, nullable=False),
        sa.Column('scope', sa.String(50), nullable=False, server_default='full'),
        sa.Column('discount_percent', sa.Numeric(5, 2), nullable=False),
        sa.Column('base_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('total_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create indexes
    op.create_index('ix_token_bundles_id', 'token_bundles', ['id'])
    op.create_index('ix_token_bundles_is_active', 'token_bundles', ['is_active'])

    # Insert default bundles
    op.execute("""
        INSERT INTO token_bundles (id, name, description, token_count, duration_hours, scope, discount_percent, base_price, total_price, is_active, created_at)
        VALUES
            (gen_random_uuid(), 'Starter Pack', '5 tokens for beginners - 10% off', 5, 24, 'full', 10.00, 90.00, 81.00, true, NOW()),
            (gen_random_uuid(), 'Pro Bundle', '10 tokens for power users - 15% off', 10, 24, 'full', 15.00, 180.00, 153.00, true, NOW()),
            (gen_random_uuid(), 'Ultimate Package', '20 weekly tokens - 20% off', 20, 168, 'full', 20.00, 2000.00, 1600.00, true, NOW()),
            (gen_random_uuid(), 'Certificates Bundle', '10 certificates-only tokens - 15% off', 10, 24, 'certificates_only', 15.00, 180.00, 153.00, true, NOW())
    """)


def downgrade() -> None:
    """Drop token_bundles table and indexes."""
    op.drop_index('ix_token_bundles_is_active', 'token_bundles')
    op.drop_index('ix_token_bundles_id', 'token_bundles')
    op.drop_table('token_bundles')
