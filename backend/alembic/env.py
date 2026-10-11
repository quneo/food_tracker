from alembic import context

from app import models  # noqa: F401 -- register every table in the metadata
from app.database import Base, engine

if context.is_offline_mode():
    context.configure(url=str(engine.url), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with engine.connect() as connection:
        # Batch migrations recreate tables; foreign keys must be off while the old table is
        # dropped. The pragma has no effect inside a transaction, so set it on the raw
        # connection before SQLAlchemy begins one.
        connection.connection.dbapi_connection.execute("PRAGMA foreign_keys=OFF")
        context.configure(
            connection=connection, target_metadata=Base.metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"Foreign key check failed after migration: {broken}")
