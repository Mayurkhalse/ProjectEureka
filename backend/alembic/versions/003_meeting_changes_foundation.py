"""Additive migration for DGIPR meeting changes data foundation

Revision ID: 003_meeting_changes_foundation
Revises: 002_copilot_audit
Create Date: 2026-10-22 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '003_meeting_changes_foundation'
down_revision: Union[str, None] = '002_copilot_audit'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. district_positions
    op.create_table(
        'district_positions',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('district_code', sa.String(10), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('designation_en', sa.String(255), nullable=False),
        sa.Column('designation_mr', sa.String(255), nullable=False),
        sa.Column('person_name', sa.String(255), nullable=False),
        sa.Column('responsibilities_en', sa.Text(), nullable=True),
        sa.Column('responsibilities_mr', sa.Text(), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_district_positions_district_code', 'district_positions', ['district_code'])
    op.create_index('ix_district_positions_category', 'district_positions', ['category'])

    # 2. scheme_hoardings
    op.create_table(
        'scheme_hoardings',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('district_code', sa.String(10), nullable=False),
        sa.Column('scheme_name_en', sa.String(255), nullable=False),
        sa.Column('scheme_name_mr', sa.String(255), nullable=False),
        sa.Column('department_code', sa.String(100), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lon', sa.Float(), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('size', sa.String(50), nullable=False),
        sa.Column('installed_on', sa.String(50), nullable=True),
        sa.Column('expires_on', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='ACTIVE'),
        sa.Column('announcement_en', sa.Text(), nullable=True),
        sa.Column('announcement_mr', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(1024), nullable=True),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_scheme_hoardings_district_code', 'scheme_hoardings', ['district_code'])
    op.create_index('ix_scheme_hoardings_department_code', 'scheme_hoardings', ['department_code'])

    # 3. clippings
    op.create_table(
        'clippings',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('district_code', sa.String(10), nullable=False),
        sa.Column('headline', sa.String(500), nullable=False),
        sa.Column('outlet', sa.String(255), nullable=False),
        sa.Column('language', sa.String(20), nullable=False, server_default='mr'),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source_url', sa.String(1024), nullable=False),
        sa.Column('clipping_image_url', sa.String(1024), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_clippings_district_code', 'clippings', ['district_code'])

    # 4. social_posts
    op.create_table(
        'social_posts',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('district_code', sa.String(10), nullable=False),
        sa.Column('platform', sa.String(50), nullable=False),
        sa.Column('handle', sa.String(100), nullable=False),
        sa.Column('post_url', sa.String(1024), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('engagement', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_social_posts_district_code', 'social_posts', ['district_code'])

    # 5. tv_clips
    op.create_table(
        'tv_clips',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('district_code', sa.String(10), nullable=False),
        sa.Column('channel', sa.String(100), nullable=False),
        sa.Column('programme', sa.String(255), nullable=False),
        sa.Column('clip_url', sa.String(1024), nullable=False),
        sa.Column('aired_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('start_offset_sec', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transcript_text', sa.Text(), nullable=True),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_tv_clips_district_code', 'tv_clips', ['district_code'])

    # 6. ticker_items
    op.create_table(
        'ticker_items',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('kind', sa.String(50), nullable=False),
        sa.Column('text_en', sa.Text(), nullable=False),
        sa.Column('text_mr', sa.Text(), nullable=False),
        sa.Column('link_url', sa.String(1024), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provenance', sa.String(50), nullable=False, server_default='synthetic'),
    )

    # 7. webauthn_credentials
    op.create_table(
        'webauthn_credentials',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('credential_id', sa.String(512), nullable=False, unique=True),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('sign_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transports', sa.String(255), nullable=True),
        sa.Column('label', sa.String(255), nullable=True, server_default='Face ID / Windows Hello'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_webauthn_credentials_user_id', 'webauthn_credentials', ['user_id'])
    op.create_index('ix_webauthn_credentials_credential_id', 'webauthn_credentials', ['credential_id'])

    # 8. transcript_segments
    op.create_table(
        'transcript_segments',
        sa.Column('id', sa.String(100), primary_key=True),
        sa.Column('stream_id', sa.String(100), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('language', sa.String(10), nullable=False, server_default='mr'),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('machine_generated', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_transcript_segments_stream_id', 'transcript_segments', ['stream_id'])


def downgrade() -> None:
    op.drop_table('transcript_segments')
    op.drop_table('webauthn_credentials')
    op.drop_table('ticker_items')
    op.drop_table('tv_clips')
    op.drop_table('social_posts')
    op.drop_table('clippings')
    op.drop_table('scheme_hoardings')
    op.drop_table('district_positions')
