import os
from collections.abc import Generator

import pytest

os.environ["QUAKERELAY_DATABASE_URL"] = "sqlite:////tmp/quakerelay-pytest.db"
os.environ["QUAKERELAY_DATA_DIR"] = "/tmp/quakerelay-pytest-data"
os.environ["QUAKERELAY_SECRET_KEY"] = "UOMW9DPw_lU6bxPKwJYoH3h6f1P2GFZ4Q1jC0oA6j6g="
os.environ["QUAKERELAY_ENABLE_COLLECTOR"] = "false"

from quakerelay.db import Base  # noqa: E402
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        yield value
    Base.metadata.drop_all(engine)
