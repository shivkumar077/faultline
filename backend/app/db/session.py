from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

database_url = settings.DATABASE_URL.get_secret_value()
connect_args = {}
engine_kwargs = {
    "echo": settings.DB_ECHO,
    "connect_args": connect_args,
}

if not database_url.startswith("sqlite"):
    connect_args.update(
        {
            "connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
            "options": (
                f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS} "
                f"-c lock_timeout={settings.DB_LOCK_TIMEOUT_MS}"
            ),
        }
    )
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
            "pool_pre_ping": True,
        }
    )
else:
    connect_args.update(
        {
            "timeout": settings.DB_POOL_TIMEOUT,
            "check_same_thread": False,
        }
    )

engine = create_engine(database_url, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency injection generator yielding an active database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
