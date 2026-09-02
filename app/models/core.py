import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FieldType(str, enum.Enum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    FILE = "FILE"


class RequestState(str, enum.Enum):
    UNFINISHED = "UNFINISHED"
    SUBMITTED = "SUBMITTED"
    CANCELLED = "CANCELLED"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    fields: Mapped[list["ServiceField"]] = relationship(back_populates="service", cascade="all, delete-orphan")
    statuses: Mapped[list["ServiceStatus"]] = relationship(back_populates="service", cascade="all, delete-orphan")
    requests: Mapped[list["Request"]] = relationship(back_populates="service")


class ServiceField(Base):
    __tablename__ = "service_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(500))
    field_type: Mapped[FieldType] = mapped_column(Enum(FieldType, native_enum=False))
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    service: Mapped["Service"] = relationship(back_populates="fields")
    answers: Mapped[list["RequestAnswer"]] = relationship(back_populates="service_field")
    conversation_states: Mapped[list["ConversationState"]] = relationship(back_populates="current_field")


class ServiceStatus(Base):
    __tablename__ = "service_statuses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    service: Mapped["Service"] = relationship(back_populates="statuses")
    requests: Mapped[list["Request"]] = relationship(back_populates="current_status")


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index(
            "uq_unfinished_request_per_chat_id",
            "chat_id",
            unique=True,
            sqlite_where=text("state = 'UNFINISHED'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracking_code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    chat_id: Mapped[str] = mapped_column(String(128), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), index=True)
    state: Mapped[RequestState] = mapped_column(Enum(RequestState, native_enum=False), default=RequestState.UNFINISHED)
    current_status_id: Mapped[int | None] = mapped_column(ForeignKey("service_statuses.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    service: Mapped["Service"] = relationship(back_populates="requests")
    current_status: Mapped["ServiceStatus | None"] = relationship(back_populates="requests")
    answers: Mapped[list["RequestAnswer"]] = relationship(back_populates="request", cascade="all, delete-orphan")
    conversation_states: Mapped[list["ConversationState"]] = relationship(back_populates="request")


class RequestAnswer(Base):
    __tablename__ = "request_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), index=True)
    service_field_id: Mapped[int | None] = mapped_column(ForeignKey("service_fields.id", ondelete="SET NULL"), nullable=True, index=True)
    field_label_snapshot: Mapped[str] = mapped_column(String(500))
    field_type_snapshot: Mapped[FieldType] = mapped_column(Enum(FieldType, native_enum=False))
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    request: Mapped["Request"] = relationship(back_populates="answers")
    service_field: Mapped["ServiceField | None"] = relationship(back_populates="answers")


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("requests.id", ondelete="SET NULL"), nullable=True, index=True)
    current_field_id: Mapped[int | None] = mapped_column(ForeignKey("service_fields.id", ondelete="SET NULL"), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    request: Mapped["Request | None"] = relationship(back_populates="conversation_states")
    current_field: Mapped["ServiceField | None"] = relationship(back_populates="conversation_states")
