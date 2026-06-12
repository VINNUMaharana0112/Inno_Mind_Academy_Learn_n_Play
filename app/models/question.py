from sqlalchemy import Column, String, Integer, Text, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base

class Question(Base):
    __tablename__ = "questions"

    # Preserved exactly as your grading engine expects (Integer ID)
    id = Column(Integer, primary_key=True, index=True)
    
    # Tagging & Freemium Wall Logic
    syllabus_tag = Column(String(100), index=True, nullable=False)
    level = Column(Integer, default=1) # Levels 1-10 are Free. Levels 11+ trigger the Premium Wall.

    # 1. Bilingual Content Fields
    question_text = Column(Text, nullable=False)          # The default/English text
    question_text_regional = Column(Text, nullable=True)  # Hindi, Odia, Bengali, etc.
    passage_text = Column(Text, nullable=True)            # Optional reference material
    
    # 2. Options & Answers (Preserved for your array-sorting grading logic)
    options = Column(JSONB, nullable=False)               # List of available options
    correct_answers = Column(JSONB, nullable=False)       # List of the correct options
    
    # 3. Post-Match Learning
    explanation = Column(Text, nullable=True)             # Detailed solution for the end screen
    
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))