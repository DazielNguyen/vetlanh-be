"""add sounds table

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-06-11 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sounds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("filename", name="uq_sounds_filename"),
    )

    op.bulk_insert(
        sa.table(
            "sounds",
            sa.column("id", sa.String),
            sa.column("title", sa.String),
            sa.column("description", sa.Text),
            sa.column("category", sa.String),
            sa.column("filename", sa.String),
            sa.column("duration_seconds", sa.Integer),
            sa.column("sort_order", sa.Integer),
            sa.column("is_published", sa.Boolean),
        ),
        [
            {"id": "stream",         "title": "Tiếng suối chảy",       "description": "Âm thanh trong trẻo của dòng suối nhỏ chảy qua rừng núi.",        "category": "nature",     "filename": "stream.mp3",         "duration_seconds": None, "sort_order": 1,  "is_published": True},
            {"id": "rain-light",     "title": "Tiếng mưa nhẹ",          "description": "Giọt mưa rơi trên mái nhà, xua tan lo lắng.",                      "category": "nature",     "filename": "rain-light.mp3",     "duration_seconds": None, "sort_order": 2,  "is_published": True},
            {"id": "ocean-waves",    "title": "Sóng biển",               "description": "Nhịp điệu đều đặn của sóng biển.",                                 "category": "nature",     "filename": "ocean-waves.mp3",    "duration_seconds": None, "sort_order": 3,  "is_published": True},
            {"id": "forest",         "title": "Tiếng rừng sâu",          "description": "Tiếng chim hót, lá rơi trong không gian rừng nguyên sinh.",        "category": "nature",     "filename": "forest.mp3",         "duration_seconds": None, "sort_order": 4,  "is_published": True},
            {"id": "tibetan-bowl",   "title": "Chuông Tây Tạng",         "description": "Âm thanh cộng hưởng của chuông đồng giúp tập trung.",              "category": "meditation", "filename": "tibetan-bowl.mp3",   "duration_seconds": 1200, "sort_order": 5,  "is_published": True},
            {"id": "fire-crackling", "title": "Tiếng lửa crackling",     "description": "Âm thanh lửa cháy trong lò sưởi, ấm áp và thư giãn.",             "category": "meditation", "filename": "fire-crackling.mp3", "duration_seconds": None, "sort_order": 6,  "is_published": True},
            {"id": "healing-432hz",  "title": "Nhạc chữa lành 432Hz",    "description": "Âm nhạc ở tần số 432Hz hài hòa với nhịp điệu tự nhiên.",          "category": "music",      "filename": "healing-432hz.mp3",  "duration_seconds": 1800, "sort_order": 7,  "is_published": True},
            {"id": "binaural-alpha", "title": "Binaural Beats — Alpha",  "description": "Sóng não Alpha (8–12Hz) tạo trạng thái thư giãn tỉnh táo.",        "category": "music",      "filename": "binaural-alpha.mp3", "duration_seconds": 1500, "sort_order": 8,  "is_published": True},
            {"id": "binaural-theta", "title": "Binaural Beats — Theta",  "description": "Sóng Theta (4–8Hz) kích thích thiền sâu và cải thiện giấc ngủ.",  "category": "music",      "filename": "binaural-theta.mp3", "duration_seconds": 1800, "sort_order": 9,  "is_published": True},
            {"id": "white-noise",    "title": "Tiếng ồn trắng",          "description": "White noise che lấp tiếng ồn xung quanh.",                         "category": "noise",      "filename": "white-noise.mp3",    "duration_seconds": None, "sort_order": 10, "is_published": True},
            {"id": "brown-noise",    "title": "Tiếng ồn nâu",            "description": "Tần số thấp hơn white noise, giống tiếng thác nước.",             "category": "noise",      "filename": "brown-noise.mp3",    "duration_seconds": None, "sort_order": 11, "is_published": True},
            {"id": "pink-noise",     "title": "Tiếng ồn hồng",           "description": "Cân bằng giữa white và brown noise, cải thiện slow-wave sleep.",  "category": "noise",      "filename": "pink-noise.mp3",     "duration_seconds": None, "sort_order": 12, "is_published": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("sounds")
