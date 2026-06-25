"""Small management CLI.

Usage (from the backend/ directory, inside the venv):
    python manage.py create-admin --email you@example.com --password 'StrongPass1' --name 'Admin'

Creates a new admin user, or promotes an existing user (by email) to admin
and optionally resets their password.
"""
import argparse
import sys

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app import models


def create_admin(email: str, password: str, name: str) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            user.is_admin = True
            if password:
                user.password_hash = hash_password(password)
            db.commit()
            print(f"Promoted existing user to admin: {email}")
            return
        user = models.User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            upi_address="-",  # admins aren't paid collectors
            is_admin=True,
        )
        db.add(user)
        db.commit()
        print(f"Created admin user: {email}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UsmleWise CHRIST management")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin", help="Create or promote an admin user")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="Administrator")

    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.email, args.password, args.name)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
