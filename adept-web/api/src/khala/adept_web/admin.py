"""adept-web-admin — operator CLI for the auth user store (Postgres). No public signup."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from khala.adept_web.auth_store import AuthStore, PostgresAuthStore, User
from khala.adept_web.security import hash_password

MIN_PASSWORD_LEN = 8


def add_user_to_store(store: AuthStore, email: str, password: str, tenant_slug: str) -> User:
    """Core (store-injected, testable): validate + hash + create. Raises on weak
    password or duplicate email."""
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    return store.create_user(email, hash_password(password), tenant_slug=tenant_slug)


def create_tenant_in_store(store: AuthStore, slug: str, name: str) -> None:
    """Core (store-injected, testable): create a tenant by slug and name."""
    store.create_tenant(slug, name)


def _add_user_cli(email: str, tenant: str) -> int:
    dsn = os.getenv("ADEPT_DATABASE_URL")
    if not dsn:
        print("error: ADEPT_DATABASE_URL is required (auth is Postgres-only)", file=sys.stderr)
        return 1
    pw1 = getpass.getpass("password: ")
    pw2 = getpass.getpass("confirm:  ")
    if pw1 != pw2:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    try:
        user = add_user_to_store(PostgresAuthStore(dsn), email, pw1, tenant_slug=tenant)
    except Exception as exc:  # weak password / duplicate / DB error / bad tenant FK
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created user {user.email}")
    return 0


def _create_tenant_cli(slug: str, name: str) -> int:
    dsn = os.getenv("ADEPT_DATABASE_URL")
    if not dsn:
        print("error: ADEPT_DATABASE_URL is required (auth is Postgres-only)", file=sys.stderr)
        return 1
    try:
        create_tenant_in_store(PostgresAuthStore(dsn), slug, name)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created tenant {slug}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="adept-web-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add-user", help="create a user (prompts for password)")
    add.add_argument("email")
    add.add_argument("--tenant", required=True, help="tenant slug to assign the user to")

    ct = sub.add_parser("create-tenant", help="create a new tenant")
    ct.add_argument("slug", help="tenant slug (unique identifier)")
    ct.add_argument("--name", default=None, help="human-readable tenant name (defaults to slug)")

    args = parser.parse_args(argv)
    if args.cmd == "add-user":
        return _add_user_cli(args.email, args.tenant)
    if args.cmd == "create-tenant":
        return _create_tenant_cli(args.slug, args.name or args.slug)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
