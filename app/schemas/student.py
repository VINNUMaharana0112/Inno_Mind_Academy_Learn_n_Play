from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

class StudentBase(BaseModel):
    email: EmailStr
    nickname: str

class StudentCreate(StudentBase):
    password: str

class StudentLogin(BaseModel):
    email: EmailStr
    password: str

class StudentResponse(StudentBase):
    student_id: UUID | str
    lives_remaining: int
    has_unlimited_lives: bool
    trophy_count: int
    orange_diamonds: int
    red_diamonds: int
    blue_diamonds: int
    highest_level_passed: int
    rating: int

    class Config:
        from_attributes = True  # Allows Pydantic to read SQLAlchemy models