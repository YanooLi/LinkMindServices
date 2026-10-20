"""schema per SmartUrl-database-schema.md: urls, qrcodes, ai_analyses, analytics

Revision ID: 2130079820cc
Revises: d065a867035b
Create Date: 2026-10-20 01:01:37.218577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2130079820cc'
down_revision: Union[str, Sequence[str], None] = 'd065a867035b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Replace the first prototype schema (links/click_events) with the designed one; dev data only.
    op.drop_table('click_events')
    op.drop_table('links')
    op.drop_table('users')
    sa.Enum(name='analysis_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='risk_level').drop(op.get_bind(), checkfirst=True)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('auth_provider', sa.Text(), nullable=True),
    sa.Column('auth_provider_id', sa.Text(), nullable=True),
    sa.Column('first_name', sa.Text(), nullable=True),
    sa.Column('last_name', sa.Text(), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('username')
    )
    op.create_index('idx_auth_provider', 'users', ['auth_provider', 'auth_provider_id'], unique=False)
    op.create_table('urls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('original_url', sa.Text(), nullable=False),
    sa.Column('short_code', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('clicks', sa.Integer(), nullable=False),
    sa.Column('is_safe', sa.Boolean(), nullable=False),
    sa.Column('ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_urls_user', 'urls', ['user_id'], unique=False)
    op.create_index(op.f('ix_urls_short_code'), 'urls', ['short_code'], unique=True)
    op.create_table('qrcodes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('original_url', sa.Text(), nullable=False),
    sa.Column('qr_code_id', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('scans', sa.Integer(), nullable=False),
    sa.Column('is_safe', sa.Boolean(), nullable=False),
    sa.Column('ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('color', sa.String(length=7), nullable=False),
    sa.Column('style', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_qrcodes_user', 'qrcodes', ['user_id'], unique=False)
    op.create_index(op.f('ix_qrcodes_qr_code_id'), 'qrcodes', ['qr_code_id'], unique=True)
    op.create_table('ai_analyses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resource_type', sa.Text(), nullable=False),
    sa.Column('resource_id', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=True),
    sa.Column('is_safe', sa.Boolean(), nullable=False),
    sa.Column('safety_score', sa.Float(), nullable=True),
    sa.Column('threat_types', sa.JSON(), nullable=False),
    sa.Column('reasons', sa.JSON(), nullable=False),
    sa.Column('ai_provider', sa.Text(), nullable=True),
    sa.Column('google_safe_browsing_safe', sa.Boolean(), nullable=True),
    sa.Column('google_safe_browsing_threats', sa.JSON(), nullable=False),
    sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resource_type', 'resource_id')
    )
    op.create_index('idx_ai_category', 'ai_analyses', ['category'], unique=False)
    op.create_index('idx_ai_is_safe', 'ai_analyses', ['is_safe'], unique=False)
    op.create_index('idx_ai_resource', 'ai_analyses', ['resource_type', 'resource_id'], unique=False)
    op.create_table('analytics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('resource_type', sa.Text(), nullable=False),
    sa.Column('resource_id', sa.Text(), nullable=False),
    sa.Column('event_type', sa.Text(), nullable=False),
    sa.Column('event_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('device_type', sa.Text(), nullable=True),
    sa.Column('country', sa.Text(), nullable=True),
    sa.Column('referrer', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_country', 'analytics', ['country'], unique=False)
    op.create_index('idx_device_type', 'analytics', ['device_type'], unique=False)
    op.create_index('idx_event_date', 'analytics', ['event_date'], unique=False)
    op.create_index('idx_resource', 'analytics', ['resource_type', 'resource_id'], unique=False)


def downgrade() -> None:
    op.drop_table('analytics')
    op.drop_table('ai_analyses')
    op.drop_table('qrcodes')
    op.drop_table('urls')
    op.drop_table('users')
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('hashed_password', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('links',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('short_code', sa.String(length=32), nullable=False),
    sa.Column('original_url', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('click_count', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'done', 'failed', name='analysis_status'), nullable=False),
    sa.Column('risk_level', sa.Enum('unknown', 'safe', 'suspicious', 'malicious', name='risk_level'), nullable=False),
    sa.Column('risk_reasons', sa.JSON(), nullable=False),
    sa.Column('category', sa.String(length=50), nullable=True),
    sa.Column('category_source', sa.String(length=30), nullable=True),
    sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_links_owner_created', 'links', ['owner_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_links_short_code'), 'links', ['short_code'], unique=True)
    op.create_table('click_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('link_id', sa.Integer(), nullable=False),
    sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('referrer', sa.String(length=500), nullable=True),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.ForeignKeyConstraint(['link_id'], ['links.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_clicks_link_time', 'click_events', ['link_id', 'clicked_at'], unique=False)


