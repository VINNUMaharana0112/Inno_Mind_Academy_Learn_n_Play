from sqlalchemy import Column, String, Integer, Boolean, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Student(Base):
    __tablename__ = "students"

    # We use PostgreSQL's native UUID for high security
    student_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    
    full_name = Column(String(150), nullable=True) # Nullable for progressive profiling
    nickname = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Inno Mind Academy Game Economy
    lives_remaining = Column(Integer, default=3)
    trophy_count = Column(Integer, default=0)
    
    is_email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))