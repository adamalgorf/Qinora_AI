"""One-off CLI to create or update a user directly against the configured
database, bypassing the HTTP API. Needed because creating a user via
/users requires an existing admin to be logged in already - this breaks
that chicken-and-egg problem for the very first account.

Usage:
    python -m qinora.infrastructure.bootstrap_admin \
        --email farah@qinora.org --full-name "Farah" --password 1234 --role admin
"""

import argparse
import asyncio

from qinora.infrastructure.passwords import hash_password
from qinora.infrastructure.settings import PersistenceDriver, Settings


async def bootstrap_user(
    settings: Settings, *, email: str, full_name: str | None, password: str, role: str
) -> None:
    if settings.persistence_driver is PersistenceDriver.POSTGRES:
        from qinora.infrastructure.postgres import PostgresDatabase, PostgresUserRepository

        if settings.database_url is None:
            raise RuntimeError("DATABASE_URL is required when QINORA_PERSISTENCE=postgres")
        database = PostgresDatabase(settings.database_url, settings.postgres_tenant_id)
        repository = PostgresUserRepository(database)
    else:
        from qinora.infrastructure.sqlite import SQLiteDatabase, SQLiteUserRepository

        database = SQLiteDatabase(settings.sqlite_path)
        repository = SQLiteUserRepository(database)

    password_hash = hash_password(password)
    existing = await repository.find_by_email(email)
    if existing is None:
        user = await repository.create_user(
            email=email,
            full_name=full_name,
            password_hash=password_hash,
            roles=(role,),
        )
        print(f"Created user {user.email} ({user.id}) with roles {user.roles}")
    else:
        await repository.set_password(existing.id, password_hash)
        await repository.set_roles(existing.id, (role,))
        await repository.set_active(existing.id, True)
        print(f"Updated existing user {existing.email} ({existing.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default=None)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", default="admin")
    args = parser.parse_args()

    settings = Settings.from_env()
    asyncio.run(
        bootstrap_user(
            settings,
            email=args.email,
            full_name=args.full_name,
            password=args.password,
            role=args.role,
        )
    )


if __name__ == "__main__":
    main()
