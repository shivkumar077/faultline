from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine


def test_alembic_head_matches_model_metadata() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "backend" / "migrations"))

    with create_engine("sqlite:///:memory:").connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
