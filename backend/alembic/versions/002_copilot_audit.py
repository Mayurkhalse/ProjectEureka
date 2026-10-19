"""Additive migration for Open UI Copilot audit and feedback

Revision ID: 002_copilot_audit
Revises: 001_initial_schema
Create Date: 2026-10-19 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '002_copilot_audit'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_runs
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('principal_id', sa.String(100), nullable=False),
        sa.Column('principal_role', sa.String(50), nullable=False),
        sa.Column('model_id', sa.String(100), nullable=False),
        sa.Column('prompt_version_hash', sa.String(64), nullable=False),
        sa.Column('user_query', sa.Text(), nullable=False),
        sa.Column('language', sa.String(10), nullable=False, server_default='en'),
        sa.Column('tools_called', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('validation_result', sa.String(50), nullable=False, server_default='valid'),
        sa.Column('fallback_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('latency_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_agent_runs_principal_id', 'agent_runs', ['principal_id'])
    op.create_index('ix_agent_runs_created_at', 'agent_runs', ['created_at'])

    # 2. agent_tool_calls
    op.create_table(
        'agent_tool_calls',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('tool_args', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('tool_status', sa.String(50), nullable=False, server_default='success'),
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_agent_tool_calls_run_id', 'agent_tool_calls', ['run_id'])
    op.create_index('ix_agent_tool_calls_tool_name', 'agent_tool_calls', ['tool_name'])

    # 3. copilot_feedback
    op.create_table(
        'copilot_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('principal_id', sa.String(100), nullable=False),
        sa.Column('rating', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_copilot_feedback_run_id', 'copilot_feedback', ['run_id'])
    op.create_index('ix_copilot_feedback_principal_id', 'copilot_feedback', ['principal_id'])


def downgrade() -> None:
    op.drop_table('copilot_feedback')
    op.drop_table('agent_tool_calls')
    op.drop_table('agent_runs')
