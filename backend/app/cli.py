"""Operational commands. Usage (from backend/, venv active):

    python -m app.cli create-platform-admin --email you@example.com --name "Your Name"
    python -m app.cli seed-demo        # development / E2E only
    python -m app.cli purge-print-documents   # schedule daily

The password is read from a hidden prompt, never from the command line or environment.
"""

import argparse
import getpass
import sys

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_session_factory
from app.modules.printing.retention import purge_expired_documents
from app.modules.users.service import create_platform_admin
from app.providers.storage.factory import build_storage
from app.seed import seed_demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-platform-admin", help="Create a platform-wide ADMIN user")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    sub.add_parser("seed-demo", help="Create demo users and resources (development / E2E only)")
    sub.add_parser(
        "purge-print-documents",
        help="Delete student print documents past the retention period (run daily)",
    )
    args = parser.parse_args(argv)

    if args.command == "purge-print-documents":
        settings = get_settings()
        with get_session_factory()() as db:
            report = purge_expired_documents(db, build_storage(settings), settings)
        print(
            f"Purged {report.closed_orders} closed-order and {report.orphans} orphan documents ({report.storage_errors} errors)."
        )
        return 1 if report.storage_errors else 0

    if args.command == "seed-demo":
        settings = get_settings()
        if settings.is_production:
            print("Refusing to seed demo data in production.", file=sys.stderr)
            return 2
        with get_session_factory()() as db:
            info = seed_demo(db, build_storage(settings))
        print(
            "Demo data ready. Accounts:", ", ".join(v for k, v in info.items() if k != "password")
        )
        print(f"Password for all demo accounts: {info['password']}")
        return 0

    password = getpass.getpass("Password (min 10 characters): ")
    if len(password) < 10 or password != getpass.getpass("Repeat password: "):
        print("Passwords must match and be at least 10 characters.", file=sys.stderr)
        return 2

    with get_session_factory()() as db:
        try:
            user = create_platform_admin(
                db, email=args.email, password=password, full_name=args.name
            )
        except AppError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
    print(f"Created platform admin {user.email} ({user.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
