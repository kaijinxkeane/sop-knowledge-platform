"""Admin command line (run inside the api container or from backend/).

    python -m app.cli sync-config [--reset-roles]   spaces + default roles from config/
    python -m app.cli create-admin EMAIL "NAME"     first admin; prints a one-time invite token
    python -m app.cli accept-invite TOKEN           set a password for an invite (prompts)
    python -m app.cli index [--full] [--no-embed]   (re)index the vault now

Development only (refused unless SOP_ENV=development; fictional data):
    python -m app.cli seed-demo                     demo users + demo document labels
    python -m app.cli totp-code EMAIL               current two-factor code for a demo user
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import hashlib
import sys
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_engine, get_sessionmaker
from app.identity import create_user, get_user_by_email, sync_roles, sync_spaces
from app.security import passwords, totp
from app.security.tokens import hash_opaque

DEMO_PASSWORD = "demo-password-2026"
# Fictional staff of the demo training company (names match demo-vault owners).
DEMO_USERS = [
    (
        "jordan.ng@staff.example.com",
        "Jordan Ng (CEO)",
        ["employee", "core-lead", "platform-admin"],
        "core",
    ),
    ("avery.tan@staff.example.com", "Avery Tan", ["employee", "core-staff"], "core"),
    ("sam.lee@staff.example.com", "Sam Lee", ["employee", "core-staff"], "core"),
    ("morgan.lim@staff.example.com", "Morgan Lim", ["employee", "core-staff"], "core"),
    ("riley.ong@staff.example.com", "Riley Ong", ["employee", "it-lead"], "it"),
    ("casey.wong@staff.example.com", "Casey Wong", ["employee", "hr-staff", "hr-lead"], "hr"),
    ("taylor.goh@staff.example.com", "Taylor Goh (new hire)", ["employee"], None),
]


def _demo_totp_secret(email: str) -> str:
    return base64.b32encode(hashlib.sha256(f"demo-totp:{email}".encode()).digest()[:20]).decode()


def _require_dev() -> None:
    if get_settings().environment != "development":
        sys.exit("refused: demo commands only run with SOP_ENV=development")


async def cmd_sync_config(reset_roles: bool) -> None:
    async with get_sessionmaker()() as s:
        spaces = await sync_spaces(s)
        roles = await sync_roles(s, reset=reset_roles)
        await s.commit()
    print(f"spaces updated: {spaces or 'none'}; roles created: {roles or 'none'}")


async def cmd_create_admin(email: str, name: str) -> None:
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await sync_roles(s)
        user, token = await create_user(
            s,
            email=email,
            display_name=name,
            role_names=["employee", "platform-admin"],
            home_space=None,
            actor_id=None,
        )
        await s.commit()
    print(f"created admin {user.email}")
    print("one-time invite token (set the password with `accept-invite`; then sign in and")
    print(f"set up two-factor):\n\n  {token}\n")


async def cmd_accept_invite(token: str) -> None:
    from app.db.models import OneTimeToken

    password = getpass.getpass("new password: ")
    if password != getpass.getpass("repeat: "):
        sys.exit("passwords differ")
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                select(OneTimeToken).where(OneTimeToken.token_hash == hash_opaque(token))
            )
        ).scalar_one_or_none()
        if row is None or row.used_at or row.expires_at <= datetime.now(UTC):
            sys.exit("invalid or expired invite")
        from app.db.models import User

        user = await s.get(User, row.user_id)
        try:
            user.password_hash = passwords.hash_password(password)
        except passwords.PasswordPolicyError as exc:
            sys.exit(str(exc))
        row.used_at = datetime.now(UTC)
        await s.commit()
    print("password set; sign in to set up two-factor")


async def cmd_index(full: bool, no_embed: bool) -> None:
    from app.retrieval.embed import embed_documents
    from app.vault.git import GitVault
    from app.vault.indexer import Indexer

    git = GitVault(get_settings().vault_path)
    if not git.is_repo():
        sys.exit(f"vault is not a git repository: {git.root}")
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await s.commit()
    report = await Indexer(git, get_sessionmaker(), None if no_embed else embed_documents).sync(
        full=full
    )
    print(report.summary())


async def cmd_seed_demo() -> None:
    _require_dev()
    async with get_sessionmaker()() as s:
        await sync_spaces(s)
        await sync_roles(s)
        for email, name, roles, home in DEMO_USERS:
            if await get_user_by_email(s, email):
                continue
            user, _ = await create_user(
                s, email=email, display_name=name, role_names=roles, home_space=home, actor_id=None
            )
            user.password_hash = passwords.hash_password(DEMO_PASSWORD)
            user.totp_secret_enc = totp.encrypt_secret(_demo_totp_secret(email))
            user.totp_enabled = True
        await s.commit()
    print(f"demo users ready (password: {DEMO_PASSWORD}); index the vault with `index`")
    print("two-factor codes: python -m app.cli totp-code EMAIL")


def cmd_totp_code(email: str) -> None:
    _require_dev()
    if email not in {u[0] for u in DEMO_USERS}:
        sys.exit("only demo users")
    print(pyotp.TOTP(_demo_totp_secret(email)).now())


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync-config")
    p.add_argument("--reset-roles", action="store_true")
    p = sub.add_parser("create-admin")
    p.add_argument("email")
    p.add_argument("name")
    p = sub.add_parser("index")
    p.add_argument("--full", action="store_true")
    p.add_argument("--no-embed", action="store_true")
    p = sub.add_parser("accept-invite")
    p.add_argument("token")
    sub.add_parser("seed-demo")
    p = sub.add_parser("totp-code")
    p.add_argument("email")
    args = parser.parse_args(argv)

    if args.cmd == "totp-code":
        return cmd_totp_code(args.email)

    async def run() -> None:
        try:
            if args.cmd == "sync-config":
                await cmd_sync_config(args.reset_roles)
            elif args.cmd == "create-admin":
                await cmd_create_admin(args.email, args.name)
            elif args.cmd == "accept-invite":
                await cmd_accept_invite(args.token)
            elif args.cmd == "index":
                await cmd_index(args.full, args.no_embed)
            elif args.cmd == "seed-demo":
                await cmd_seed_demo()
        finally:
            await get_engine().dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
