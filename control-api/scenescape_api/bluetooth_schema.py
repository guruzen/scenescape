from __future__ import annotations

from sqlalchemy import inspect, select

from .database import (
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothAudit,
    BluetoothCalibration,
    BluetoothDeviceTelemetry,
    BluetoothMeasurement,
    BluetoothProvider,
    BluetoothRawPosition,
    BluetoothTag,
    BluetoothSurveyPoint,
    BluetoothSurveySample,
    BluetoothTrackedPosition,
)


BT01_TABLES = (
    BluetoothProvider.__table__,
    BluetoothAnchor.__table__,
    BluetoothTag.__table__,
    BluetoothCalibration.__table__,
    BluetoothAssignment.__table__,
)


def bluetooth_table_names() -> tuple[str, ...]:
  return tuple(table.name for table in BT01_TABLES)


def upgrade_bt01(engine) -> None:
  """Create only the BT-01 tables and indexes without touching existing native data."""
  for table in BT01_TABLES:
    table.create(bind=engine, checkfirst=True)


def downgrade_bt01(engine, *, allow_data_loss: bool = False) -> None:
  """Drop BT-01 tables.

  Production rollback normally disables the feature and leaves these additive
  tables in place. A physical downgrade refuses to discard Bluetooth records
  unless allow_data_loss=True is explicitly supplied.
  """
  existing = set(inspect(engine).get_table_names())
  if not allow_data_loss:
    with engine.connect() as connection:
      populated: list[str] = []
      for table in BT01_TABLES:
        if table.name not in existing:
          continue
        if connection.execute(select(table.c[0]).limit(1)).first() is not None:
          populated.append(table.name)
      if populated:
        raise RuntimeError(
            "Refusing Bluetooth schema downgrade with data in: " + ", ".join(populated)
        )

  for table in reversed(BT01_TABLES):
    table.drop(bind=engine, checkfirst=True)


BT02_TABLES = (BluetoothAudit.__table__,)


def upgrade_bt02(engine) -> None:
  """Create BT-02 audit persistence without changing BT-01 device data."""
  for table in BT02_TABLES:
    table.create(bind=engine, checkfirst=True)


BT06_TABLES = (BluetoothMeasurement.__table__,)


def upgrade_bt06(engine) -> None:
  """Create bounded raw Bluetooth measurement persistence for BT-06."""
  for table in BT06_TABLES:
    table.create(bind=engine, checkfirst=True)


BT07_TABLES = (BluetoothRawPosition.__table__,)


def upgrade_bt07(engine) -> None:
  """Create persisted raw Bluetooth positioning solves for BT-07."""
  for table in BT07_TABLES:
    table.create(bind=engine, checkfirst=True)


BT08_TABLES = (BluetoothTrackedPosition.__table__,)


def upgrade_bt08(engine) -> None:
  """Create persisted Bluetooth tracked-position storage for BT-08."""
  for table in BT08_TABLES:
    table.create(bind=engine, checkfirst=True)


BT10_TABLES = (BluetoothDeviceTelemetry.__table__,)


def upgrade_bt10(engine) -> None:
  """Create provenance-bearing Bluetooth device telemetry storage for BT-10."""
  for table in BT10_TABLES:
    table.create(bind=engine, checkfirst=True)


BT11_TABLES = (
    BluetoothSurveyPoint.__table__,
    BluetoothSurveySample.__table__,
)


def upgrade_bt11(engine) -> None:
  """Create advanced calibration survey persistence for BT-11."""
  for table in BT11_TABLES:
    table.create(bind=engine, checkfirst=True)
