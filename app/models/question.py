from sqlalchemy import Column, String, Integer, Text, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base

class Question(Base):
    __tablename__ = "questions"

    # Preserved exactly as your grading engine expects (Integer ID)
    id = Column(Integer, primary_key=True, index=True)
    
    # Tagging & Freemium Wall Logic
    syllabus_tag = Column(String(100), index=True, nullable=False)
    
    # Consolidated Level tracking (Levels 1-10 are Free. Levels 11+ trigger the Premium Wall)
    level = Column(Integer, index=True, nullable=False, default=1) 
    
    # 1. Base English Content Fields
    question_text = Column(Text, nullable=False)          # The default/English text
    passage_text = Column(Text, nullable=True)            # Optional reference material (e.g., Reading Comprehension)
    
    # 2. Options & Answers (Preserved for your array-sorting grading logic)
    options = Column(JSONB, nullable=False)               # List of available options e.g., ["A", "B", "C", "D"]
    correct_answers = Column(JSONB, nullable=False)       # List of the correct options e.g., ["A"]
    
    # 3. Post-Match Learning
    explanation = Column(Text, nullable=True)             # Detailed English solution for the end screen
    
    # 4. 🌍 The Master Multilingual Hub
    # Replaces the single 'question_text_regional' to dynamically support 
    # Odia, Tamil, Telugu, Hindi, Marathi, Kannada, Gujarati, and Bengali
    translations = Column(JSONB, nullable=True, default={}) 
    
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))