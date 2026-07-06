"""option_b_marker_split_plus_is_derived

Revision ID: 217dce22fbc5
Revises: 8e5c0954c4b5
Create Date: 2026-07-07 06:38:10.464774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '217dce22fbc5'
down_revision: Union[str, Sequence[str], None] = '8e5c0954c4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.add_column(sa.Column('marker_name_raw', sa.String(length=100), nullable=True))

    # Backfill: raw name was never historically stored — old `marker` (canonical
    # id) is the best available value. Lossy, but the only recoverable source.
    op.execute("UPDATE lab_results SET marker_name_raw = marker WHERE marker_name_raw IS NULL")

    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.alter_column(
            'marker_name_raw',
            existing_type=sa.String(length=100),
            nullable=False,
        )
        batch_op.create_index('ix_lab_results_marker_name_raw', ['marker_name_raw'])
        batch_op.drop_index('ix_lab_results_marker')
        batch_op.drop_constraint('uq_lab_result_report_marker', type_='unique')

    # Rename in its own batch — combining it with index/constraint operations above
    # trips an Alembic SQLite batch-mode bug in index carry-forward across renames.
    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.alter_column(
            'marker',
            new_column_name='marker_canonical',
            existing_type=sa.String(length=100),
            nullable=True,
        )

    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.create_index('ix_lab_results_marker_canonical', ['marker_canonical'])
        batch_op.create_unique_constraint(
            'uq_lab_result_report_marker_raw', ['lab_report_id', 'marker_name_raw']
        )
        batch_op.add_column(
            sa.Column(
                'is_derived',
                sa.Boolean(),
                server_default=sa.text('false'),
                nullable=False,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.drop_column('is_derived')
        batch_op.drop_constraint('uq_lab_result_report_marker_raw', type_='unique')
        batch_op.drop_index('ix_lab_results_marker_canonical')

    # Reverse backfill before re-imposing NOT NULL: unmapped rows have
    # marker_canonical IS NULL and would otherwise violate the restored constraint.
    op.execute(
        "UPDATE lab_results SET marker_canonical = COALESCE(marker_canonical, marker_name_raw)"
    )

    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.alter_column(
            'marker_canonical',
            new_column_name='marker',
            existing_type=sa.String(length=100),
            nullable=False,
        )

    with op.batch_alter_table('lab_results') as batch_op:
        batch_op.create_index('ix_lab_results_marker', ['marker'])
        batch_op.create_unique_constraint('uq_lab_result_report_marker', ['lab_report_id', 'marker'])
        batch_op.drop_index('ix_lab_results_marker_name_raw')
        batch_op.drop_column('marker_name_raw')
