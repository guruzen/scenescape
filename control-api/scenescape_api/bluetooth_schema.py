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


def _populated_tables(engine, tables) -> list[str]:
  existing = set(inspect(engine).get_table_names())
  populated: list[str] = []
  with engine.connect() as connection:
    for table in tables:
      if table.name not in existing:
        continue
      if connection.execute(select(table.c[0]).limit(1)).first() is not None:
        populated.append(table.name)
  return populated


def _drop_tables_safely(
    engine,
    tables,
    *,
    allow_data_loss: bool,
    label: str,
) -> None:
  if not allow_data_loss:
    populated = _populated_tables(engine, tables)
    if populated:
      raise RuntimeError(
          f"Refusing {label} schema downgrade with data in: "
          + ", ".join(populated)
      )
  for table in reversed(tuple(tables)):
    table.drop(bind=engine, checkfirst=True)


def upgrade_bt01(engine) -> None:
  """Create only the BT-01 tables and indexes without touching existing native data."""
  for table in BT01_TABLES:
    table.create(bind=engine, checkfirst=True)


def downgrade_bt01(engine, *, allow_data_loss: bool = False) -> None:
  """Drop BT-01 tables after an explicit data-loss decision."""
  _drop_tables_safely(
      engine,
      BT01_TABLES,
      allow_data_loss=allow_data_loss,
      label="Bluetooth BT-01",
  )


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



def bluetooth_all_table_names() -> tuple[str, ...]:
  tables = (
      *BT01_TABLES,
      *BT02_TABLES,
      *BT06_TABLES,
      *BT07_TABLES,
      *BT08_TABLES,
      *BT10_TABLES,
      *BT11_TABLES,
  )
  return tuple(table.name for table in tables)


def downgrade_all_bluetooth(engine, *, allow_data_loss: bool = False) -> None:
  """Physically remove the additive Bluetooth schema.

  This is not the normal application rollback path. The recommended rollback
  is to disable the subsystem and roll back the application/Helm release while
  retaining Bluetooth tables. A physical schema rollback is provided for
  controlled test/disaster-recovery scenarios and refuses to delete any
  populated Bluetooth table unless allow_data_loss=True is explicit.
  """
  tables = (
      *BT01_TABLES,
      *BT02_TABLES,
      *BT06_TABLES,
      *BT07_TABLES,
      *BT08_TABLES,
      *BT10_TABLES,
      *BT11_TABLES,
  )
  if not allow_data_loss:
    populated = _populated_tables(engine, tables)
    if populated:
      raise RuntimeError(
          "Refusing Bluetooth full schema downgrade with data in: "
          + ", ".join(populated)
      )

  # Drop dependents before the control-plane identity tables.
  for group in (
      BT11_TABLES,
      BT10_TABLES,
      BT08_TABLES,
      BT07_TABLES,
      BT06_TABLES,
      BT02_TABLES,
      BT01_TABLES,
  ):
    for table in reversed(group):
      table.drop(bind=engine, checkfirst=True)
