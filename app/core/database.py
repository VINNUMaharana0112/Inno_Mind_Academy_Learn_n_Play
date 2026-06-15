import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Fetch the Neon database URL from your .env file
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 1. THE OPTIMIZATION: Connection Pooling Engine
# We add pool_size, max_overflow, and pool_pre_ping to keep connections alive and fast.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=5,             # Keep 5 connections open and ready at all times
    max_overflow=10,         # Allow up to 10 extra connections during traffic spikes
    pool_pre_ping=True,      # ALWAYS test the connection before using it (fixes Neon disconnects)
    pool_recycle=1800        # Refresh connections every 30 minutes to prevent staleness
)

# 2. Session Local
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. Base Model
Base = declarative_base()

# 4. Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()