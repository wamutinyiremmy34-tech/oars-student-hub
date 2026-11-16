import uuid

import pytest
from sqlalchemy import MetaData, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.schema import CreateTable

from app.db.base import NAMING_CONVENTION, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.session import get_engine


class ScratchBase(DeclarativeBase):
    """Separate metadata so this scratch table never leaks into Alembic's autogenerate."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Widget(UUIDPrimaryKeyMixin, TimestampMixin, ScratchBase):
    __tablename__ = "widget_test"
    name: Mapped[str] = mapped_column(String(50), unique=True)


def test_conventions_produce_expected_ddl() -> None:
    ddl = str(CreateTable(Widget.__table__).compile(dialect=postgresql.dialect()))
    assert "gen_random_uuid()" in ddl
    assert "CONSTRAINT pk_widget_test PRIMARY KEY (id)" in ddl
    assert "CONSTRAINT uq_widget_test_name UNIQUE (name)" in ddl
    assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl
    assert "updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in ddl


@pytest.mark.integration
def test_mixins_populate_uuid_and_timestamps_in_postgres() -> None:
    engine = get_engine()
    ScratchBase.metadata.drop_all(engine, checkfirst=True)
    ScratchBase.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            widget = Widget(name="first")
            session.add(widget)
            session.commit()
            assert isinstance(widget.id, uuid.UUID)
            assert widget.created_at.tzinfo is not None
            created_at = widget.created_at

            widget.name = "renamed"
            session.commit()
            session.refresh(widget)
            assert widget.created_at == created_at
            assert widget.updated_at > created_at
    finally:
        ScratchBase.metadata.drop_all(engine, checkfirst=True)
