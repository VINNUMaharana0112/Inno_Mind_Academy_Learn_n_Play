import enum
import uuid
from sqlalchemy import Column, String, Integer, Boolean, Enum
from app.core.database import Base 

class RoundLevel(enum.Enum):
    ENTRY = "entry"
    EXPERT = "expert"
    GENIUS = "genius"

class StudentTier(enum.Enum):
    FREEMIUM = "freemium"
    PREMIUM = "premium"
    ELITE = "elite"

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True)
    nickname = Column(String, unique=True, index=True)
    password_hash = Column(String)

    # --- THE CORE GAME ECONOMY ---
    # Every student now starts with exactly 150 lives for the Entry Round
    lives_remaining = Column(Integer, default=150)
    has_unlimited_lives = Column(Boolean, default=False)
    
    # Universal currency (carried forward across all rounds)
    trophy_count = Column(Integer, default=0)

    # --- THE ADVANCED DIAMOND ECONOMY ---
    # Earned by maintaining high averages (70%, 80%, 90%)
    orange_diamonds = Column(Integer, default=0)
    red_diamonds = Column(Integer, default=0)
    blue_diamonds = Column(Integer, default=0)

    # --- PROGRESSION TRACKING ---
    highest_round_unlocked = Column(Enum(RoundLevel), default=RoundLevel.ENTRY)
    highest_level_passed = Column(Integer, default=0)
    rating = Column(Integer, default=0)

    # --- LIFETIME ANALYTICS ---
    # Required to calculate the 70%/80%/90% accuracy thresholds for diamonds
    total_questions_attempted = Column(Integer, default=0)
    total_correct_answers = Column(Integer, default=0)
    
    # Kept for future monetization pivots
    tier = Column(Enum(StudentTier), default=StudentTier.FREEMIUM)