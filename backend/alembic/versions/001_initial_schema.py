"""Initial schema creation for Project EUREKA

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. source_registry
    op.create_table(
        'source_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('lane', sa.String(50), nullable=False),
        sa.Column('base_url', sa.String(2048), nullable=False),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('poll_interval_sec', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('last_polled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_source_registry_lane', 'source_registry', ['lane'])
    op.create_index('ix_source_registry_is_active', 'source_registry', ['is_active'])

    # 2. ingestion_runs
    op.create_table(
        'ingestion_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('source_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='STARTED'),
        sa.Column('items_ingested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_ingestion_runs_source_id', 'ingestion_runs', ['source_id'])
    op.create_index('ix_ingestion_runs_status', 'ingestion_runs', ['status'])

    # 3. raw_events
    op.create_table(
        'raw_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('ingestion_run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ingestion_runs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('source_registry.id', ondelete='CASCADE'), nullable=False),
        sa.Column('lane', sa.String(50), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('raw_content', sa.Text(), nullable=False),
        sa.Column('raw_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_raw_events_ingestion_run_id', 'raw_events', ['ingestion_run_id'])
    op.create_index('ix_raw_events_source_id', 'raw_events', ['source_id'])
    op.create_index('ix_raw_events_lane', 'raw_events', ['lane'])
    op.create_index('ix_raw_events_payload_hash', 'raw_events', ['payload_hash'])
    op.create_index('ix_raw_events_ingested_at', 'raw_events', ['ingested_at'])
    op.create_index('ix_raw_events_source_hash', 'raw_events', ['source_id', 'payload_hash'])

    # 4. normalized_records
    op.create_table(
        'normalized_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('raw_event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('raw_events.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('cleaned_text', sa.Text(), nullable=False),
        sa.Column('detected_language', sa.String(20), nullable=False),
        sa.Column('script', sa.String(50), nullable=False),
        sa.Column('normalized_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('entities', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('claims', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_normalized_records_lang', 'normalized_records', ['detected_language'])
    op.create_index('ix_normalized_records_timestamp', 'normalized_records', ['normalized_timestamp'])

    # 5. canonical_events
    op.create_table(
        'canonical_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('primary_language', sa.String(20), nullable=False),
        sa.Column('district_code', sa.String(50), nullable=True),
        sa.Column('district_name', sa.String(100), nullable=True),
        sa.Column('department_code', sa.String(50), nullable=True),
        sa.Column('department_name', sa.String(100), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending_review'),
        sa.Column('verification_status', sa.String(50), nullable=False, server_default='UNVERIFIED'),
        sa.Column('sentiment_label', sa.String(50), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_canonical_events_district', 'canonical_events', ['district_code'])
    op.create_index('ix_canonical_events_dept', 'canonical_events', ['department_code'])
    op.create_index('ix_canonical_events_status', 'canonical_events', ['status'])
    op.create_index('ix_canonical_events_verification', 'canonical_events', ['verification_status'])
    op.create_index('ix_canonical_events_first_detected', 'canonical_events', ['first_detected_at'])

    # 6. event_source_links
    op.create_table(
        'event_source_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('canonical_event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('canonical_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('normalized_record_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('normalized_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('bound_by', sa.String(100), nullable=False, server_default='SemIf-OpenJev'),
        sa.Column('bound_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_event_source_links_canonical_id', 'event_source_links', ['canonical_event_id'])
    op.create_index('ix_event_source_links_record_id', 'event_source_links', ['normalized_record_id'])
    op.create_index('ix_event_source_unique', 'event_source_links', ['canonical_event_id', 'normalized_record_id'], unique=True)

    # 7. binding_decisions
    op.create_table(
        'binding_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('normalized_record_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('normalized_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('canonical_event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('canonical_events.id', ondelete='SET NULL'), nullable=True),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('decision_type', sa.String(50), nullable=False),
        sa.Column('logic_primitive', sa.String(50), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_binding_decisions_record_id', 'binding_decisions', ['normalized_record_id'])
    op.create_index('ix_binding_decisions_canonical_id', 'binding_decisions', ['canonical_event_id'])
    op.create_index('ix_binding_decisions_type', 'binding_decisions', ['decision_type'])
    op.create_index('ix_binding_decisions_decided_at', 'binding_decisions', ['decided_at'])

    # 8. fact_check_tickets
    op.create_table(
        'fact_check_tickets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('canonical_event_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('canonical_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('claim_text', sa.Text(), nullable=False),
        sa.Column('is_rumor', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('event_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('refuted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('refuted_within_sla_90m', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('status', sa.String(50), nullable=False, server_default='OPEN'),
        sa.Column('assigned_to', sa.String(100), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_fact_check_tickets_canonical_id', 'fact_check_tickets', ['canonical_event_id'])
    op.create_index('ix_fact_check_tickets_is_rumor', 'fact_check_tickets', ['is_rumor'])
    op.create_index('ix_fact_check_tickets_event_ts', 'fact_check_tickets', ['event_timestamp'])
    op.create_index('ix_fact_check_tickets_sla', 'fact_check_tickets', ['refuted_within_sla_90m'])
    op.create_index('ix_fact_check_tickets_status', 'fact_check_tickets', ['status'])

    # 9. pillar_score_snapshots
    op.create_table(
        'pillar_score_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('volume_score', sa.Float(), nullable=False),
        sa.Column('tat_score', sa.Float(), nullable=False),
        sa.Column('sentiment_score', sa.Float(), nullable=False),
        sa.Column('crisis_sla_score', sa.Float(), nullable=False),
        sa.Column('total_composite_score', sa.Float(), nullable=False),
        sa.Column('calculation_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_pillar_scores_window_start', 'pillar_score_snapshots', ['window_start'])
    op.create_index('ix_pillar_scores_window_end', 'pillar_score_snapshots', ['window_end'])
    op.create_index('ix_pillar_scores_created_at', 'pillar_score_snapshots', ['created_at'])

    # 10. human_review_actions
    op.create_table(
        'human_review_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_type', sa.String(100), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reviewer_id', sa.String(100), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('previous_state', sa.String(50), nullable=False),
        sa.Column('new_state', sa.String(50), nullable=False),
        sa.Column('action_taken', sa.String(50), nullable=False),
        sa.Column('comments', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_human_review_entity', 'human_review_actions', ['entity_type', 'entity_id'])
    op.create_index('ix_human_review_role', 'human_review_actions', ['role'])
    op.create_index('ix_human_review_created_at', 'human_review_actions', ['created_at'])

    # 11. outbox_events
    op.create_table(
        'outbox_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('aggregate_type', sa.String(50), nullable=False),
        sa.Column('aggregate_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_outbox_events_aggregate', 'outbox_events', ['aggregate_type', 'aggregate_id'])
    op.create_index('ix_outbox_events_status', 'outbox_events', ['status'])
    op.create_index('ix_outbox_events_status_created', 'outbox_events', ['status', 'created_at'])


def downgrade() -> None:
    op.drop_table('outbox_events')
    op.drop_table('human_review_actions')
    op.drop_table('pillar_score_snapshots')
    op.drop_table('fact_check_tickets')
    op.drop_table('binding_decisions')
    op.drop_table('event_source_links')
    op.drop_table('canonical_events')
    op.drop_table('normalized_records')
    op.drop_table('raw_events')
    op.drop_table('ingestion_runs')
    op.drop_table('source_registry')
