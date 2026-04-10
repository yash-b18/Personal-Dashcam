"""
Root pytest configuration.

Sets required environment variables to safe test defaults before any
test module is collected. This ensures the API and database modules
initialize with SQLite (no PostgreSQL needed) in the test environment.
"""

import os

# Override DB to SQLite so no PostgreSQL connection is needed in tests.
# These run before any test module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("R2_ACCOUNT_ID", "test-account")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test-key-id")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("R2_BUCKET_NAME", "test-bucket")
os.environ.setdefault("R2_PUBLIC_URL", "https://test.r2.dev")
os.environ.setdefault("R2_MAIN_FOLDER", "videos")
os.environ.setdefault("R2_FRONT_FOLDER", "Front")
os.environ.setdefault("R2_REAR_FOLDER", "Rear")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")
