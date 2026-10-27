"""add score_details column to document_compliance_results

Revision ID: a3b5c8d1e2f4
Revises: 30eb39c0001a
Create Date: 2026-05-21 10:00:00.000000
"""

import json

from alembic import op
import sqlalchemy as sa


revision = 'a3b5c8d1e2f4'
down_revision = '1c3d5e7f9a2b'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    op.add_column(
        'document_compliance_results',
        sa.Column('score_details', sa.JSON(), nullable=True, server_default='{}'),
    )

    if bind.dialect.name == 'postgresql':
        op.execute(
            sa.text(
                """
                UPDATE document_compliance_results
                SET score_details = COALESCE(reference_basis::jsonb -> 'score_details', '{}'::jsonb),
                    reference_basis = COALESCE(reference_basis::jsonb - 'score_details', '{}'::jsonb)
                WHERE reference_basis IS NOT NULL
                  AND reference_basis::jsonb ? 'score_details'
                """
            )
        )
        return

    rows = bind.execute(
        sa.text(
            'SELECT id, reference_basis FROM document_compliance_results '
            'WHERE reference_basis IS NOT NULL'
        )
    ).fetchall()
    for row_id, raw in rows:
        if not raw:
            continue
        try:
            payload = raw if isinstance(raw, dict) else json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict) or 'score_details' not in payload:
            continue
        score_details = payload.pop('score_details') or {}
        bind.execute(
            sa.text(
                'UPDATE document_compliance_results '
                'SET score_details = :score_details, reference_basis = :reference_basis '
                'WHERE id = :id'
            ),
            {
                'score_details': json.dumps(score_details),
                'reference_basis': json.dumps(payload),
                'id': row_id,
            },
        )


def downgrade():
    op.drop_column('document_compliance_results', 'score_details')
