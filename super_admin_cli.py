#!/usr/bin/env python
"""UMSHADO server-only account administration.

Examples:
    python super_admin_cli.py bootstrap --name "UMSHADO Admin" --email admin@example.com --phone 26876123456
    python super_admin_cli.py create-test-user --name "Test Couple 1" --email test1@example.com --phone 26876000001
    python super_admin_cli.py create-test-user --name "Test Couple 2" --email test2@example.com --phone 26876000002
    python super_admin_cli.py assign-admin user@example.com
    python super_admin_cli.py revoke-admin user@example.com
    python super_admin_cli.py grant-test-access user@example.com
    python super_admin_cli.py revoke-test-access user@example.com
    python super_admin_cli.py reset-password user@example.com
    python super_admin_cli.py list

The first super admin is bootstrapped once. Every later privileged operation
re-verifies that super admin's password. No administrator role can be created
through the public web application.
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import User
from app.routes import normalize_phone


class SuperAdminError(Exception):
    """A safe, user-facing CLI validation or authentication error."""


TEST_ACCOUNT_LIMIT = 2


def _user_by_email(email):
    return db.session.scalar(select(User).where(User.email == email.strip().lower()))


def _validated_phone(phone):
    normalized = normalize_phone(phone)
    if not normalized.startswith("268") or len(normalized) != 11:
        raise SuperAdminError("Enter a valid Eswatini phone number.")
    return normalized


def _prompt_password(label):
    password = getpass.getpass(f"{label}: ")
    confirmation = getpass.getpass(f"Confirm {label.lower()}: ")
    if password != confirmation:
        raise SuperAdminError("Passwords do not match.")
    if len(password) < 8:
        raise SuperAdminError("Password must be at least 8 characters.")
    return password


def _authenticate_super_admin():
    email = input("Super admin email: ").strip().lower()
    password = getpass.getpass("Super admin password: ")
    user = _user_by_email(email)
    if user is None or not user.is_super_admin:
        raise SuperAdminError(f'"{email}" is not a super admin account.')
    if not user.check_password(password):
        raise SuperAdminError("Incorrect super admin password.")
    return user


def _new_user(name, email, phone, password):
    email = email.strip().lower()
    phone = _validated_phone(phone)
    if not name.strip():
        raise SuperAdminError("Name is required.")
    if _user_by_email(email):
        raise SuperAdminError(f"Email already exists: {email}")
    if db.session.scalar(select(User).where(User.phone_number == phone)):
        raise SuperAdminError(f"Phone number already exists: {phone}")
    user = User(name=name.strip(), email=email, phone_number=phone)
    user.set_password(password)
    db.session.add(user)
    return user


def bootstrap(name, email, phone, password):
    if db.session.scalar(select(User).where(User.is_super_admin.is_(True))):
        raise SuperAdminError("A super admin already exists.")
    user = _new_user(name, email, phone, password)
    user.is_super_admin = True
    user.is_admin = True
    db.session.commit()
    return user


def create_test_user(name, email, phone, password):
    _authenticate_super_admin()
    test_count = db.session.scalar(
        select(db.func.count()).select_from(User).where(User.has_test_access.is_(True))
    )
    if test_count >= TEST_ACCOUNT_LIMIT:
        raise SuperAdminError(
            f"The {TEST_ACCOUNT_LIMIT} unrestricted test-account slots are already in use."
        )
    user = _new_user(name, email, phone, password)
    user.has_test_access = True
    db.session.commit()
    return user


def update_access(target_email, field, enabled):
    actor = _authenticate_super_admin()
    target = _user_by_email(target_email)
    if target is None:
        raise SuperAdminError(f"User not found: {target_email}")
    if target.id == actor.id and not enabled:
        raise SuperAdminError("The active super admin cannot revoke their own access.")
    if target.is_super_admin and field == "is_admin" and not enabled:
        raise SuperAdminError("A super admin cannot be demoted with this command.")
    if field == "has_test_access" and enabled and not target.has_test_access:
        test_count = db.session.scalar(
            select(db.func.count()).select_from(User).where(User.has_test_access.is_(True))
        )
        if test_count >= TEST_ACCOUNT_LIMIT:
            raise SuperAdminError(
                f"The {TEST_ACCOUNT_LIMIT} unrestricted test-account slots are already in use."
            )
    setattr(target, field, enabled)
    db.session.commit()
    return target


def reset_password(target_email, password):
    actor = _authenticate_super_admin()
    target = _user_by_email(target_email)
    if target is None:
        raise SuperAdminError(f"User not found: {target_email}")
    if target.is_super_admin and target.id != actor.id:
        raise SuperAdminError("One super admin cannot reset another super admin's password.")
    target.set_password(password)
    db.session.commit()
    return target


def list_users():
    _authenticate_super_admin()
    return db.session.scalars(select(User).order_by(User.id)).all()


def build_parser():
    parser = argparse.ArgumentParser(description="UMSHADO super-admin CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    for command in ("bootstrap", "create-test-user"):
        item = commands.add_parser(command)
        item.add_argument("--name", required=True)
        item.add_argument("--email", required=True)
        item.add_argument("--phone", required=True)

    for command in ("assign-admin", "revoke-admin", "grant-test-access", "revoke-test-access", "reset-password"):
        item = commands.add_parser(command)
        item.add_argument("email", help="target account email")

    commands.add_parser("list")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    app = create_app()
    try:
        with app.app_context():
            if args.command == "bootstrap":
                user = bootstrap(args.name, args.email, args.phone, _prompt_password(f"Password for {args.email}"))
                print(f"Super admin created: {user.email} (id={user.id})")
            elif args.command == "create-test-user":
                password = _prompt_password(f"Password for {args.email}")
                user = create_test_user(args.name, args.email, args.phone, password)
                print(f"Unrestricted test user created: {user.email} (id={user.id})")
            elif args.command == "assign-admin":
                user = update_access(args.email, "is_admin", True)
                print(f"Administrator access granted: {user.email}")
            elif args.command == "revoke-admin":
                user = update_access(args.email, "is_admin", False)
                print(f"Administrator access revoked: {user.email}")
            elif args.command == "grant-test-access":
                user = update_access(args.email, "has_test_access", True)
                print(f"Test access granted: {user.email}")
            elif args.command == "revoke-test-access":
                user = update_access(args.email, "has_test_access", False)
                print(f"Test access revoked: {user.email}")
            elif args.command == "reset-password":
                password = _prompt_password(f"New password for {args.email}")
                user = reset_password(args.email, password)
                print(f"Password reset: {user.email}")
            elif args.command == "list":
                users = list_users()
                print(f'{"ID":<5} {"Email":<34} {"Admin":<7} {"Super":<7} Test')
                for user in users:
                    print(
                        f"{user.id:<5} {user.email:<34} {str(user.is_admin):<7} "
                        f"{str(user.is_super_admin):<7} {user.has_test_access}"
                    )
                print(f"\n{len(users)} user(s) total.")
    except (SuperAdminError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
