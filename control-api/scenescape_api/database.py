import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
  pass


_engine = None
_Session = None


def utcnow():
  return datetime.now(timezone.utc)


def database_url():
  explicit = os.getenv("DATABASE_URL")
  if explicit:
    return explicit
  host = os.getenv("DBHOST")
  if not host:
    return "sqlite:///./scenescape-native.db"
  user = quote_plus(os.getenv("DBUSER", "scenescape"))
  password = quote_plus(os.getenv("DBPASSWORD", ""))
  db = quote_plus(os.getenv("DBNAME", "scenescape"))
  port = os.getenv("DBPORT", "5432")
  return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


class Resource(Base):
  __tablename__ = "native_resources"
  __table_args__ = (UniqueConstraint("kind", "uid", name="uq_native_resources_kind_uid"),)
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  kind: Mapped[str] = mapped_column(String(40), index=True)
  uid: Mapped[str] = mapped_column(String(96), index=True)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  payload: Mapped[dict] = mapped_column(JSON, default=dict)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Observation(Base):
  __tablename__ = "native_observations"
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), index=True)
  topic: Mapped[str] = mapped_column(Text)
  observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
  payload: Mapped[dict] = mapped_column(JSON)


class Event(Base):
  __tablename__ = "native_events"
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), index=True)
  topic: Mapped[str] = mapped_column(Text)
  observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
  payload: Mapped[dict] = mapped_column(JSON)


class Incident(Base):
  __tablename__ = "native_incidents"
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
  scene_id: Mapped[str] = mapped_column(String(96), index=True)
  title: Mapped[str] = mapped_column(String(240))
  status: Mapped[str] = mapped_column(String(32), default="new")
  assignee: Mapped[str] = mapped_column(String(160), default="")
  notes: Mapped[list] = mapped_column(JSON, default=list)
  audit: Mapped[list] = mapped_column(JSON, default=list)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Heartbeat(Base):
  __tablename__ = "native_heartbeats"
  key: Mapped[str] = mapped_column(String(64), primary_key=True)
  state: Mapped[str] = mapped_column(String(32))
  details: Mapped[dict] = mapped_column(JSON, default=dict)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothProvider(Base):
  __tablename__ = "native_bluetooth_providers"
  __table_args__ = (
      UniqueConstraint("name", name="uq_native_bluetooth_providers_name"),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  name: Mapped[str] = mapped_column(String(160), nullable=False)
  kind: Mapped[str] = mapped_column(String(64), default="generic")
  state: Mapped[str] = mapped_column(String(32), default="configured", index=True)
  capabilities: Mapped[list] = mapped_column(JSON, default=list)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothAnchor(Base):
  __tablename__ = "native_bluetooth_anchors"
  __table_args__ = (
      UniqueConstraint("serial_number", name="uq_native_bluetooth_anchors_serial"),
      UniqueConstraint(
          "provider_id",
          "provider_device_id",
          name="uq_native_bluetooth_anchors_provider_device",
      ),
      Index("ix_native_bluetooth_anchors_scene_state", "scene_id", "state"),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
  scene_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
  provider_id: Mapped[str | None] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_providers.uid", ondelete="SET NULL"),
      nullable=True,
      index=True,
  )
  provider_device_id: Mapped[str | None] = mapped_column(String(192), nullable=True)
  bluetooth_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
  manufacturer: Mapped[str | None] = mapped_column(String(160), nullable=True)
  model: Mapped[str | None] = mapped_column(String(160), nullable=True)
  hardware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  firmware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  state: Mapped[str] = mapped_column(String(32), default="commissioned", index=True)
  capabilities: Mapped[list] = mapped_column(JSON, default=list)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothTag(Base):
  __tablename__ = "native_bluetooth_tags"
  __table_args__ = (
      UniqueConstraint("serial_number", name="uq_native_bluetooth_tags_serial"),
      UniqueConstraint(
          "provider_id",
          "provider_device_id",
          name="uq_native_bluetooth_tags_provider_device",
      ),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
  provider_id: Mapped[str | None] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_providers.uid", ondelete="SET NULL"),
      nullable=True,
      index=True,
  )
  provider_device_id: Mapped[str | None] = mapped_column(String(192), nullable=True)
  bluetooth_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
  manufacturer: Mapped[str | None] = mapped_column(String(160), nullable=True)
  model: Mapped[str | None] = mapped_column(String(160), nullable=True)
  hardware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  firmware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  state: Mapped[str] = mapped_column(String(32), default="commissioned", index=True)
  capabilities: Mapped[list] = mapped_column(JSON, default=list)
  battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
  battery_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
  battery_status: Mapped[str] = mapped_column(String(32), default="unknown")
  battery_source: Mapped[str | None] = mapped_column(String(96), nullable=True)
  battery_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothAssignment(Base):
  __tablename__ = "native_bluetooth_assignments"
  __table_args__ = (
      Index(
          "uq_native_bluetooth_assignments_active_tag",
          "tag_uid",
          unique=True,
          sqlite_where=text("valid_to IS NULL"),
          postgresql_where=text("valid_to IS NULL"),
      ),
      Index("ix_native_bluetooth_assignments_entity", "entity_type", "entity_id"),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  tag_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_tags.uid"),
      nullable=False,
      index=True,
  )
  entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
  entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
  display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
  valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
  reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
  created_by: Mapped[str] = mapped_column(String(160), nullable=False)
  closed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothCalibration(Base):
  __tablename__ = "native_bluetooth_calibrations"
  __table_args__ = (
      UniqueConstraint(
          "anchor_uid",
          "calibration_revision",
          name="uq_native_bluetooth_calibrations_anchor_revision",
      ),
      Index(
          "uq_native_bluetooth_calibrations_active_anchor",
          "anchor_uid",
          unique=True,
          sqlite_where=text("state = 'active'"),
          postgresql_where=text("state = 'active'"),
      ),
      Index("ix_native_bluetooth_calibrations_scene_state", "scene_id", "state"),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  anchor_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_anchors.uid"),
      nullable=False,
      index=True,
  )
  scene_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  calibration_revision: Mapped[int] = mapped_column(Integer, nullable=False)
  state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
  x_m: Mapped[float] = mapped_column(Float, nullable=False)
  y_m: Mapped[float] = mapped_column(Float, nullable=False)
  z_m: Mapped[float] = mapped_column(Float, nullable=False)
  yaw_deg: Mapped[float] = mapped_column(Float, default=0.0)
  pitch_deg: Mapped[float] = mapped_column(Float, default=0.0)
  roll_deg: Mapped[float] = mapped_column(Float, default=0.0)
  z_source: Mapped[str] = mapped_column(String(32), default="measured")
  details: Mapped[dict] = mapped_column(JSON, default=dict)
  created_by: Mapped[str] = mapped_column(String(160), nullable=False)
  revision: Mapped[int] = mapped_column(Integer, default=1)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothAudit(Base):
  __tablename__ = "native_bluetooth_audit"
  __table_args__ = (
      Index("ix_native_bluetooth_audit_resource", "resource_type", "resource_uid"),
      Index("ix_native_bluetooth_audit_scene_time", "scene_id", "observed_at"),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  actor: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
  action: Mapped[str] = mapped_column(String(64), nullable=False)
  resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
  resource_uid: Mapped[str] = mapped_column(String(96), nullable=False)
  scene_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
  details: Mapped[dict] = mapped_column(JSON, default=dict)
  observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BluetoothMeasurement(Base):
  __tablename__ = "native_bluetooth_measurements"
  __table_args__ = (
      UniqueConstraint(
          "provider_id",
          "session_id",
          "sequence",
          name="uq_native_bluetooth_measurements_provider_session_sequence",
      ),
      Index(
          "ix_native_bluetooth_measurements_scene_tag_time",
          "scene_id",
          "tag_uid",
          "source_timestamp",
      ),
      Index(
          "ix_native_bluetooth_measurements_anchor_tag_time",
          "anchor_uid",
          "tag_uid",
          "source_timestamp",
      ),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  anchor_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_anchors.uid"),
      nullable=False,
      index=True,
  )
  tag_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_tags.uid"),
      nullable=False,
      index=True,
  )
  provider_id: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_providers.uid"),
      nullable=False,
      index=True,
  )
  session_id: Mapped[str] = mapped_column(String(96), nullable=False)
  sequence: Mapped[int] = mapped_column(Integer, nullable=False)
  source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
  method: Mapped[str] = mapped_column(String(32), nullable=False)
  distance_m: Mapped[float] = mapped_column(Float, nullable=False)
  distance_stddev_m: Mapped[float] = mapped_column(Float, nullable=False)
  rssi_dbm: Mapped[float | None] = mapped_column(Float, nullable=True)
  azimuth_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
  elevation_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
  nlos_probability: Mapped[float] = mapped_column(Float, nullable=False)
  quality: Mapped[float] = mapped_column(Float, nullable=False)
  provider_details: Mapped[dict] = mapped_column(JSON, default=dict)


class BluetoothRawPosition(Base):
  __tablename__ = "native_bluetooth_raw_positions"
  __table_args__ = (
      Index(
          "ix_native_bluetooth_raw_positions_scene_tag_time",
          "scene_id",
          "tag_uid",
          "source_timestamp",
      ),
      Index(
          "ix_native_bluetooth_raw_positions_state_time",
          "state",
          "source_timestamp",
      ),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  tag_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_tags.uid"),
      nullable=False,
      index=True,
  )
  source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  x_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  y_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  z_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  dimension: Mapped[str] = mapped_column(String(16), nullable=False)
  state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
  horizontal_uncertainty_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  vertical_uncertainty_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  score: Mapped[float] = mapped_column(Float, nullable=False)
  anchors_visible: Mapped[int] = mapped_column(Integer, nullable=False)
  anchors_used: Mapped[int] = mapped_column(Integer, nullable=False)
  residual_rms_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  gdop: Mapped[float | None] = mapped_column(Float, nullable=True)
  method: Mapped[str] = mapped_column(String(32), nullable=False)
  solver_name: Mapped[str] = mapped_column(String(64), nullable=False)
  solver_version: Mapped[str] = mapped_column(String(32), nullable=False)
  diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BluetoothTrackedPosition(Base):
  __tablename__ = "native_bluetooth_tracked_positions"
  __table_args__ = (
      Index(
          "ix_native_bluetooth_tracked_positions_scene_tag_time",
          "scene_id",
          "tag_uid",
          "source_timestamp",
      ),
      Index(
          "ix_native_bluetooth_tracked_positions_state_time",
          "state",
          "source_timestamp",
      ),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  tag_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_tags.uid"),
      nullable=False,
      index=True,
  )
  source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  x_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  y_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  z_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  vx_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
  vy_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
  vz_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
  heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
  state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
  predicted: Mapped[bool] = mapped_column(default=False, nullable=False)
  horizontal_uncertainty_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  vertical_uncertainty_m: Mapped[float | None] = mapped_column(Float, nullable=True)
  score: Mapped[float] = mapped_column(Float, nullable=False)
  anchors_used: Mapped[int] = mapped_column(Integer, nullable=False)
  method: Mapped[str] = mapped_column(String(32), nullable=False)
  solver_name: Mapped[str] = mapped_column(String(64), nullable=False)
  solver_version: Mapped[str] = mapped_column(String(32), nullable=False)
  tracker_name: Mapped[str] = mapped_column(String(64), nullable=False)
  tracker_version: Mapped[str] = mapped_column(String(32), nullable=False)
  provenance: Mapped[dict] = mapped_column(JSON, default=dict)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BluetoothDeviceTelemetry(Base):
  __tablename__ = "native_bluetooth_device_telemetry"
  __table_args__ = (
      Index(
          "ix_native_bluetooth_device_telemetry_device_time",
          "device_type",
          "device_uid",
          "observed_at",
      ),
      Index(
          "ix_native_bluetooth_device_telemetry_provider_time",
          "provider_id",
          "observed_at",
      ),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  device_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
  device_uid: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  provider_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  source: Mapped[str] = mapped_column(String(64), nullable=False)
  observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
  battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
  battery_voltage_v: Mapped[float | None] = mapped_column(Float, nullable=True)
  battery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
  manufacturer: Mapped[str | None] = mapped_column(String(160), nullable=True)
  model: Mapped[str | None] = mapped_column(String(160), nullable=True)
  hardware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  firmware_revision: Mapped[str | None] = mapped_column(String(96), nullable=True)
  details: Mapped[dict] = mapped_column(JSON, default=dict)


class BluetoothSurveyPoint(Base):
  __tablename__ = "native_bluetooth_survey_points"
  __table_args__ = (
      Index("ix_native_bluetooth_survey_points_scene_state", "scene_id", "state"),
  )

  uid: Mapped[str] = mapped_column(String(96), primary_key=True)
  scene_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
  name: Mapped[str] = mapped_column(String(160), nullable=False)
  x_m: Mapped[float] = mapped_column(Float, nullable=False)
  y_m: Mapped[float] = mapped_column(Float, nullable=False)
  z_m: Mapped[float] = mapped_column(Float, nullable=False)
  state: Mapped[str] = mapped_column(String(32), default="open", index=True)
  created_by: Mapped[str] = mapped_column(String(160), nullable=False)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
  updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BluetoothSurveySample(Base):
  __tablename__ = "native_bluetooth_survey_samples"
  __table_args__ = (
      Index(
          "ix_native_bluetooth_survey_samples_point_anchor_time",
          "survey_point_uid",
          "anchor_uid",
          "observed_at",
      ),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  survey_point_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_survey_points.uid"),
      nullable=False,
      index=True,
  )
  anchor_uid: Mapped[str] = mapped_column(
      String(96),
      ForeignKey("native_bluetooth_anchors.uid"),
      nullable=False,
      index=True,
  )
  distance_m: Mapped[float] = mapped_column(Float, nullable=False)
  distance_stddev_m: Mapped[float] = mapped_column(Float, nullable=False)
  quality: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
  observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
  details: Mapped[dict] = mapped_column(JSON, default=dict)


def get_engine():
  global _engine, _Session
  url = database_url()
  if _engine is None or str(_engine.url) != url:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)
  return _engine


def sessions():
  get_engine()
  return _Session
