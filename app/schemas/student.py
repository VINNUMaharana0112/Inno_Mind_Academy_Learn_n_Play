from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional

class StudentCreate(BaseModel):
    email: EmailStr
    nickname: str
    password: str

class StudentResponse(BaseModel):
    student_id: UUID
    nickname: str
    email: str
    
    # Game Economy & Stats
    lives_remaining: int
    trophy_count: int
    rating: int
    
    # --- NEW: DUAL-PATH ECONOMY TRACKERS ---
    has_unlimited_lives: bool
    highest_level_passed: int
    total_questions_attempted: int
    total_correct_answers: int
    
    # Tier & Content
    tier: str
    preferred_language: str
    
    # Progressive Profiling 
    full_name: Optional[str] = None
    mobile_no: Optional[str] = None
    address: Optional[str] = None
    is_email_verified: bool
    is_phone_verified: bool
    
    # Elite Profiling
    age: Optional[int] = None
    photo_url: Optional[str] = None
    education_details: Optional[str] = None
    target_exam: Optional[str] = None

    class Config:
        from_attributes = True

class StudentLogin(BaseModel):
    email: EmailStr
    password: str