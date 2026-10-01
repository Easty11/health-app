"""add hr_samples and user_hrmax (Q159 stage 2: source-neutral HR zoning)

`hr_samples` — raw heart-rate samples, source-neutral (`source`, `source_package`), unique on
(user_id, sample_time, source, source_package) so a re-posted sample is insert-or-ignore.
Health Connect heart-rate bpm was persisted nowhere (only a daily median); this is where it lives.

`user_hrmax` — a user's HRmax in force from a date, append-only, provenance a closed set
(`tested`, `observed`; never `estimated`), unique on (user_id, effective_from). Written only by
`scripts/set_hrmax.py`.

Additive and non-destructive: two new tables, nothing altered. Both are empty until the code
that fills them deploys. Hand-written CHECK constraint (autogenerate never produces them; see
SCHEMA.md caveats).

Revision ID: b4d6f8a1c3e5
Revises: a9c3e5f7b1d2
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b4d6f8a1c3e5'
down_revision: Union[str, Sequence[str], None] = 'a9c3e5f7b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'hr_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('sample_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bpm', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_package', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'sample_time', 'source', 'source_package', name='uq_hr_sample'),
    )
    op.create_index('ix_hr_samples_id', 'hr_samples', ['id'])
    op.create_index('ix_hr_samples_user_id', 'hr_samples', ['user_id'])

    op.create_table(
        'user_hrmax',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('hrmax_bpm', sa.Integer(), nullable=False),
        sa.Column('provenance', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'effective_from', name='uq_user_hrmax_effective'),
        sa.CheckConstraint("provenance IN ('tested', 'observed')", name='ck_user_hrmax_provenance'),
    )
    op.create_index('ix_user_hrmax_id', 'user_hrmax', ['id'])
    op.create_index('ix_user_hrmax_user_id', 'user_hrmax', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_hrmax_user_id', table_name='user_hrmax')
    op.drop_index('ix_user_hrmax_id', table_name='user_hrmax')
    op.drop_table('user_hrmax')
    op.drop_index('ix_hr_samples_user_id', table_name='hr_samples')
    op.drop_index('ix_hr_samples_id', table_name='hr_samples')
    op.drop_table('hr_samples')
