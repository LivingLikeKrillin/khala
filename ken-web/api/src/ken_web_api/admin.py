"""ken-web-admin — operator CLI for the auth user store (Postgres). No public signup."""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from ken_web_api.auth_store import AuthStore, PostgresAuthStore, User
from ken_web_api.security import hash_password

MIN_PASSWORD_LEN = 8


def add_user_to_store(store: AuthStore, email: str, password: str) -> User:
    """Core (store-injected, testable): validate + hash + create. Raises on weak
    password or duplicate email."""
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    return store.create_user(email, hash_password(password))


def _add_user_cli(email: str) -> int:
    dsn = os.getenv("KEN_DATABASE_URL")
    if not dsn:
        print("error: KEN_DATABASE_URL is required (auth is Postgres-only)", file=sys.stderr)
        return 1
    pw1 = getpass.getpass("password: ")
    pw2 = getpass.getpass("confirm:  ")
    if pw1 != pw2:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    try:
        user = add_user_to_store(PostgresAuthStore(dsn), email, pw1)
    except Exception as exc:  # weak password / duplicate / DB error
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"created user {user.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ken-web-admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add-user", help="create a user (prompts for password)")
    add.add_argument("email")
    args = parser.parse_args(argv)
    if args.cmd == "add-user":
        return _add_user_cli(args.email)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
