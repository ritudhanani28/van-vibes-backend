import os
import re
import sys
import uuid
import click

# Ensure backend root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
import app.db.base  # noqa: F401 - ensures all models are registered on Base.metadata
from app.modules.accounts.models import User
from app.modules.menu.models import Category, MenuItem
from app.modules.orders.models import Order, OrderItem
from app.modules.sessions.models import BillingInvoice, DiningSession
from app.modules.settings.models import CafeSettings
from app.modules.tables.models import Table

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email_format(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email.strip()))


def ensure_database_schema():
    """Ensure database tables exist before querying or creating records."""
    # 1. Try applying Alembic migrations if alembic.ini is present
    try:
        from alembic.config import Config
        from alembic import command

        alembic_ini = os.path.join(BASE_DIR, "alembic.ini")
        if os.path.exists(alembic_ini):
            alembic_cfg = Config(alembic_ini)
            alembic_cfg.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
            command.upgrade(alembic_cfg, "head")
            return
    except Exception:
        pass

    # 2. Fallback to direct SQLAlchemy create_all
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        click.secho(f"Warning: Table auto-creation notice: {exc}", fg="yellow")


@click.group()
def cli():
    """Vaan Vibes Cafe & Restro Backend CLI."""
    pass


@cli.command("createsuperuser")
@click.option("--email", "-e", default=None, help="Admin superuser email address.")
@click.option("--name", "-n", default=None, help="Admin superuser full name.")
@click.option("--password", "-p", default=None, help="Admin superuser password.")
@click.option("--no-input", is_flag=True, default=False, help="Run non-interactively.")
def createsuperuser(email, name, password, no_input):
    """
    Create an ADMIN superuser interactively or non-interactively.
    Prompts for Email, Password, and Re-enter Password.
    Strictly assigns role=ADMIN.
    """
    is_tty = sys.stdin.isatty()

    click.echo("==================================================")
    click.echo("   Vaan Vibes - Create Superuser (Admin Only)    ")
    click.echo("==================================================")

    # 1. Prompt or validate Email
    while not email:
        if no_input:
            click.secho("Error: --email is required in non-interactive mode.", fg="red", err=True)
            sys.exit(1)
        email_input = click.prompt("Email", type=str).strip().lower()
        if not email_input:
            click.secho("Error: Email cannot be empty.", fg="red", err=True)
            continue
        if not validate_email_format(email_input):
            click.secho("Error: Invalid email format. Example: admin@vaanvibes.com", fg="red", err=True)
            continue
        email = email_input

    email = email.strip().lower()
    if not validate_email_format(email):
        click.secho(f"Error: Invalid email format: {email}", fg="red", err=True)
        sys.exit(1)

    # 2. Prompt or default Name
    if not name:
        if no_input or not is_tty:
            name = "Admin Manager"
        else:
            name = click.prompt("Full Name", default="Admin Manager", show_default=True).strip()
    name = (name or "").strip() or "Admin Manager"

    # 3. Prompt or validate Password & Re-enter Password
    if not password:
        if no_input:
            click.secho("Error: --password is required in non-interactive mode.", fg="red", err=True)
            sys.exit(1)

        while True:
            pwd = click.prompt("Password", hide_input=is_tty)
            if len(pwd) < 6:
                click.secho("Error: Password must be at least 6 characters long.", fg="red", err=True)
                if not is_tty:
                    sys.exit(1)
                continue

            pwd_confirm = click.prompt("Re-enter Password", hide_input=is_tty)
            if pwd != pwd_confirm:
                click.secho("Error: Passwords do not match. Please try again.", fg="red", err=True)
                if not is_tty:
                    sys.exit(1)
                continue

            password = pwd
            break
    else:
        if len(password) < 6:
            click.secho("Error: Password must be at least 6 characters long.", fg="red", err=True)
            sys.exit(1)

    # 4. Auto-create tables if database is fresh
    ensure_database_schema()

    # 5. Check existing user in Database & save with ADMIN role
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            click.secho(f"Notice: User with email \x27{email}\x27 already exists (Current Role: {existing_user.role}).", fg="yellow")
            if not no_input and is_tty:
                confirm = click.confirm(
                    f"Do you want to update \x27{email}\x27 to ADMIN role with this new password?",
                    default=True,
                )
                if not confirm:
                    click.echo("Operation cancelled. No changes made.")
                    return

            existing_user.name = name
            existing_user.password_hash = hash_password(password)
            existing_user.role = "ADMIN"  # Strictly ADMIN
            existing_user.is_active = True
            existing_user.shift = "All-Day"
            existing_user.assigned_station = "Control Desk"
            db.commit()
            click.echo("")
            click.secho(f"✓ Superuser \x27{email}\x27 successfully updated! (Role: ADMIN)", fg="green", bold=True)
            click.echo("==================================================")
        else:
            new_admin = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                password_hash=hash_password(password),
                role="ADMIN",  # Strictly ADMIN
                shift="All-Day",
                assigned_station="Control Desk",
                is_active=True,
            )
            db.add(new_admin)
            db.commit()
            click.echo("")
            click.secho(f"✓ Superuser \x27{email}\x27 created successfully! (Role: ADMIN)", fg="green", bold=True)
            click.echo("==================================================")
    except Exception as exc:
        db.rollback()
        click.secho(f"Database error while creating superuser: {exc}", fg="red", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command("seed")
def seed():
    """Seed cafe settings, tables, and menu items (preserves users)."""
    from app.db.seed import seed_database
    seed_database()


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
