"""add contact_number to users

Revision ID: 0002_add_contact_number
Revises: 0001_initial_schema
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_add_contact_number'
down_revision: Union[str, Sequence[str], None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('users', sa.Column('contact_number', sa.String(length=50), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'contact_number')
