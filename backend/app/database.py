from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Create PostgreSQL URL
SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

# Log that we're connecting to PostgreSQL (without exposing credentials)
logger.info(f"Connecting to PostgreSQL at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")

# Create engine instance with proper arguments depending on environment
if settings.ENVIRONMENT == "development":
    # Echo SQL statements in development
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        echo=True
    )
else:
    # More efficient settings for production
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        pool_size=5, 
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        echo=False
    )

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Dependency
def get_db():
    """
    Dependency function that yields a SQLAlchemy database session
    
    This function creates a new SQLAlchemy SessionLocal that will be used
    for a single request, and then closed once the request is finished.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()  # Auto-commit successful transactions
    except Exception:
        db.rollback()  # Rollback in case of exceptions
        raise
    finally:
        db.close()  # Always close the session