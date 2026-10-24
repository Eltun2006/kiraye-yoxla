import os

# Must run before backend.config is imported: never let tests touch the development database.
# Default: throwaway SQLite. Set TEST_DATABASE_URL to run the same tests against PostgreSQL.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_kiraye.db")


def reset_db() -> None:
    """Empty database with the current schema (on PostgreSQL: migrations run again from scratch)."""
    from backend.db import Base, engine, init_db

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    init_db()
