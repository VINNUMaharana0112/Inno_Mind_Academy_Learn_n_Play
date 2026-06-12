from sqlalchemy import Column, String, Integer, Boolean, DateTime, text, Enum
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.core.database import Base

class StudentTier(str, enum.Enum):
    FREEMIUM = "Freemium"
    PREMIUM = "Premium"
    ELITE = "Elite"

class Student(Base):
    __tablename__ = "students"

    student_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()"))
    
    # 1. Freemium / Core Authentication
    nickname = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=True) 
    mobile_no = Column(String(20), nullable=True)
    
    # 2. Inno Mind Academy Game Economy
    lives_remaining = Column(Integer, default=3)
    trophy_count = Column(Integer, default=0)
    rating = Column(Integer, default=0) 
    
    # --- NEW: DUAL-PATH ECONOMY TRACKERS ---
    has_unlimited_lives = Column(Boolean, default=False)
    highest_level_passed = Column(Integer, default=0)
    total_questions_attempted = Column(Integer, default=0)
    total_correct_answers = Column(Integer, default=0)
    
    # 3. Tier & Content Management
    tier = Column(Enum(StudentTier), default=StudentTier.FREEMIUM, nullable=False)
    preferred_language = Column(String(50), default="English")
    
    # 4. Premium Verification & Data
    address = Column(String(500), nullable=True)
    is_email_verified = Column(Boolean, default=False)
    is_phone_verified = Column(Boolean, default=False)
    
    # 5. Elite Data
    age = Column(Integer, nullable=True)
    photo_url = Column(String(500), nullable=True)
    education_details = Column(String(500), nullable=True)
    target_exam = Column(String(100), default="SCHOLAR")

    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))