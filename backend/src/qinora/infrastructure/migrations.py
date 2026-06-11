import os
from collections.abc import Iterable
from pathlib import Path

import psycopg


def iter_migration_files(path: Path) -> list[Path]:
    return sorted(file for file in path.glob("*.sql") if file.is_file())


def run_migrations(database_url: str, migration_files: Iterable[Path]) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            create table if not exists public.schema_migrations (
              version text primary key,
              applied_at timestamptz not null default now()
            )
            """
        )

        for migration_file in migration_files:
            version = migration_file.name
            cursor.execute(
                "select 1 from public.schema_migrations where version = %s",
                (version,),
            )
            if cursor.fetchone() is not None:
                continue

            cursor.execute(migration_file.read_text(encoding="utf-8"))
            cursor.execute(
                "insert into public.schema_migrations (version) values (%s)",
                (version,),
            )
            applied.append(version)

    return applied


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations")

    migrations_path = Path(os.getenv("QINORA_MIGRATIONS_PATH", "migrations"))
    applied = run_migrations(database_url, iter_migration_files(migrations_path))
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("No migrations to apply")


if __name__ == "__main__":
    main()
