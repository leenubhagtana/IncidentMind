import os
import tempfile

_database = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_database.name}"

import fakeredis
import pytest

import app.redis_client

# Must be replaced before any module does `from app.redis_client import ...`.
app.redis_client.redis_client = fakeredis.FakeRedis(decode_responses=True)

from app.database import Base, engine


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.redis_client.redis_client.flushall()
    yield
