from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def get_db_session():
    engine = create_engine(
        get_settings().supabase_database_url.get_secret_value(), pool_pre_ping=True
    )
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
