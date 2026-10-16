"""
Encryption at rest for calendar credentials
(product/core/field_encryption.py — ADR-2026-10-16 finding F4, increment I5).

Covers: key resolution (env key / dev fallback with a single warning /
production fail-fast), JSON round-trip, legacy plaintext-row compatibility,
and transparent ORM handling (ciphertext on disk, plaintext in the model,
lazy re-encryption on save). The DB-backed tests run against DATABASE_URL,
same as the rest of the product suite (Postgres in CI).
"""

import base64
import logging
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from product.core import field_encryption
from product.db.models import User
from product.db.repositories import BaseRepository
from product.db.session import get_db_session, init_db

TEST_FERNET_KEY = base64.urlsafe_b64encode(b"fedcba9876543210fedcba9876543210").decode()

CREDENTIALS = {
    "provider": "google",
    "access_token": "ya29.fake-access-token",
    "refresh_token": "1//fake-refresh-token",
}


@pytest.fixture(autouse=True)
def fresh_encryption_state(monkeypatch):
    """Give every test a clean key cache and a default test key."""
    monkeypatch.setenv("PRODUCT_FIELD_ENCRYPTION_KEY", TEST_FERNET_KEY)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    field_encryption.reset_cache()
    yield
    field_encryption.reset_cache()


class TestKeyResolution:
    def test_env_key_is_used(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_FIELD_ENCRYPTION_KEY", TEST_FERNET_KEY)
        token = field_encryption.encrypt_json(CREDENTIALS)
        # The token must decrypt with the configured key, not the dev key.
        from cryptography.fernet import Fernet
        import json as jsonlib
        payload = jsonlib.loads(Fernet(TEST_FERNET_KEY).decrypt(token).decode())
        assert payload == CREDENTIALS

    def test_missing_key_in_dev_uses_documented_key_and_warns_once(self, monkeypatch, caplog):
        monkeypatch.delenv("PRODUCT_FIELD_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        with caplog.at_level(logging.WARNING, logger="product.core.field_encryption"):
            token = field_encryption.encrypt_json(CREDENTIALS)
            field_encryption.encrypt_json(CREDENTIALS)
        warnings = [r for r in caplog.records if "PRODUCT_FIELD_ENCRYPTION_KEY" in r.getMessage()]
        assert len(warnings) == 1
        assert field_encryption.decrypt_json(token) == CREDENTIALS

    def test_missing_key_in_test_env_also_uses_dev_key(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_FIELD_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "test")
        assert field_encryption.decrypt_json(
            field_encryption.encrypt_json(CREDENTIALS)
        ) == CREDENTIALS

    def test_production_without_key_fails_fast(self, monkeypatch):
        monkeypatch.delenv("PRODUCT_FIELD_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError, match="PRODUCT_FIELD_ENCRYPTION_KEY"):
            field_encryption.initialize()
        with pytest.raises(RuntimeError, match="PRODUCT_FIELD_ENCRYPTION_KEY"):
            field_encryption.get_fernet()

    def test_invalid_key_fails_with_clear_message(self, monkeypatch):
        monkeypatch.setenv("PRODUCT_FIELD_ENCRYPTION_KEY", "not-a-fernet-key")
        with pytest.raises(RuntimeError, match="not a valid Fernet key"):
            field_encryption.initialize()


class TestEncryptDecrypt:
    def test_round_trip_nested_json(self):
        value = {"a": {"b": [1, 2, 3]}, "unicode": "héllo", "none": None}
        assert field_encryption.decrypt_json(field_encryption.encrypt_json(value)) == value

    def test_none_passes_through(self):
        assert field_encryption.encrypt_json(None) is None
        assert field_encryption.decrypt_json(None) is None

    def test_legacy_plaintext_dict_is_returned_as_is(self):
        # Rows written before encryption landed stored raw JSON.
        assert field_encryption.decrypt_json(CREDENTIALS) == CREDENTIALS

    def test_legacy_plaintext_string_is_returned_as_is(self):
        assert field_encryption.decrypt_json("not-a-token") == "not-a-token"

    def test_tokens_are_not_plaintext(self):
        token = field_encryption.encrypt_json(CREDENTIALS)
        assert CREDENTIALS["access_token"] not in token
        assert CREDENTIALS["refresh_token"] not in token


@pytest_asyncio.fixture
async def db():
    """Ensure tables exist; unique org per test, cleaned up afterwards."""
    await init_db()
    org_id = f"org_enc_{uuid.uuid4().hex[:12]}"
    yield org_id
    async with get_db_session() as session:
        await session.execute(text(f"DELETE FROM users WHERE org_id = '{org_id}'"))


@pytest.mark.asyncio
class TestCalendarCredentialsAtRest:
    async def test_orm_round_trip(self, db):
        org_id = db
        async with get_db_session() as session:
            session.add(User(
                id=f"user_{uuid.uuid4().hex[:12]}",
                org_id=org_id,
                tenant_id=org_id,
                email=f"{org_id}@example.com",
                name="Calendar User",
                calendar_provider="google",
                calendar_credentials=CREDENTIALS,
            ))

        async with get_db_session() as session:
            result = await session.execute(select(User).where(User.org_id == org_id))
            loaded = result.scalar_one()
            assert loaded.calendar_credentials == CREDENTIALS

    async def test_no_credential_plaintext_in_db(self, db):
        org_id = db
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        async with get_db_session() as session:
            session.add(User(
                id=user_id,
                org_id=org_id,
                tenant_id=org_id,
                email=f"{org_id}@example.com",
                name="Calendar User",
                calendar_provider="google",
                calendar_credentials=CREDENTIALS,
            ))

        async with get_db_session() as session:
            # Raw column read (no ORM decryption) must be ciphertext.
            result = await session.execute(
                text("SELECT calendar_credentials FROM users WHERE id = :id"),
                {"id": user_id},
            )
            raw = result.scalar_one()
            assert isinstance(raw, str)
            assert CREDENTIALS["access_token"] not in raw
            assert CREDENTIALS["refresh_token"] not in raw
            # And it must decrypt back to the original credentials.
            assert field_encryption.decrypt_json(raw) == CREDENTIALS

    async def test_legacy_plaintext_row_reads_transparently(self, db):
        org_id = db
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        # Insert a row the way the old code did: raw JSON, no encryption.
        async with get_db_session() as session:
            await session.execute(
                text(
                    "INSERT INTO users (id, org_id, tenant_id, email, name,"
                    " calendar_provider, calendar_credentials, active, created_at,"
                    " updated_at) VALUES (:id, :org, :org, :email, 'Legacy User',"
                    " 'google', :creds::jsonb, true, now(), now())"
                ),
                {"id": user_id, "org": org_id, "email": f"{org_id}-legacy@example.com",
                 "creds": '{"provider": "google", "access_token": "legacy-plain"}'},
            )

        async with get_db_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            loaded = result.scalar_one()
            assert loaded.calendar_credentials == {"provider": "google", "access_token": "legacy-plain"}

    async def test_repository_layer_is_transparent(self, db):
        org_id = db
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        async with get_db_session() as session:
            repo = BaseRepository(session, User)
            created = await repo.create({
                "id": user_id,
                "org_id": org_id,
                "tenant_id": org_id,
                "email": f"{org_id}-repo@example.com",
                "name": "Repo User",
                "calendar_credentials": CREDENTIALS,
            })
            assert created["calendar_credentials"] == CREDENTIALS

        async with get_db_session() as session:
            repo = BaseRepository(session, User)
            fetched = await repo.get(user_id, org_id)
            assert fetched["calendar_credentials"] == CREDENTIALS
            # Raw storage is still ciphertext.
            result = await session.execute(
                text("SELECT calendar_credentials FROM users WHERE id = :id"),
                {"id": user_id},
            )
            raw = result.scalar_one()
            assert CREDENTIALS["access_token"] not in raw

    async def test_lazy_migration_reencrypts_on_save(self, db):
        org_id = db
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        async with get_db_session() as session:
            await session.execute(
                text(
                    "INSERT INTO users (id, org_id, tenant_id, email, name,"
                    " calendar_provider, calendar_credentials, active, created_at,"
                    " updated_at) VALUES (:id, :org, :org, :email, 'Legacy User',"
                    " 'google', :creds::jsonb, true, now(), now())"
                ),
                {"id": user_id, "org": org_id, "email": f"{org_id}-mig@example.com",
                 "creds": '{"provider": "google", "access_token": "legacy-plain"}'},
            )

        async with get_db_session() as session:
            repo = BaseRepository(session, User)
            await repo.update(user_id, org_id, {"name": "Migrated User"})

        async with get_db_session() as session:
            result = await session.execute(
                text("SELECT calendar_credentials, name FROM users WHERE id = :id"),
                {"id": user_id},
            )
            raw, name = result.one()
            assert name == "Migrated User"
            assert "legacy-plain" not in raw  # now ciphertext at rest
            assert field_encryption.decrypt_json(raw) == {
                "provider": "google",
                "access_token": "legacy-plain",
            }
