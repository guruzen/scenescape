from __future__ import annotations

from sqlalchemy import inspect, select

from .database import (
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothCalibration,
    BluetoothProvider,
    BluetoothTag,
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
