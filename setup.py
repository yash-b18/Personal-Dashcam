"""
DashcamIQ project setup script.

Handles environment validation, directory creation, and initial
database migration to get the project ready to run.

Usage:
    python setup.py
"""

import os
import subprocess
import sys
from pathlib import Path


REQUIRED_DIRS = [
    "data/raw",
    "data/processed",
    "data/outputs/experiment",
    "models",
    "notebooks",
]

REQUIRED_ENV_VARS = [
    "DATABASE_URL",
    "REDIS_URL",
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET_NAME",
]


def create_directories() -> None:
    """Create required data and model directories if they don't exist."""
    for dir_path in REQUIRED_DIRS:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        gitkeep = path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    print("[✓] Directories created")


def check_env_vars() -> bool:
    """Validate that all required environment variables are set."""
    from dotenv import load_dotenv

    load_dotenv()

    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        print(f"[✗] Missing environment variables: {', '.join(missing)}")
        print("    Copy .env.example to .env and fill in the values.")
        return False
    print("[✓] Environment variables validated")
    return True


def run_migrations() -> None:
    """Run Alembic database migrations."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[✗] Migration failed:\n{result.stderr}")
        sys.exit(1)
    print("[✓] Database migrations applied")


def main() -> None:
    """Run full project setup."""
    print("Setting up DashcamIQ...\n")
    create_directories()
    env_ok = check_env_vars()
    if not env_ok:
        print("\nSetup incomplete — fix missing env vars and rerun.")
        sys.exit(1)
    run_migrations()
    print("\nDashcamIQ setup complete. Run `uvicorn app:app --reload` to start.")


if __name__ == "__main__":
    main()
