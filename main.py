import os
import json
import random
import httpx
from enum import Enum
from typing import Dict, List
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

# --- LOCAL APP IMPORTS ---
from app.core.database import get_db, engine
from app.core.security import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
from app.models import student as student_model
from app.schemas import student as student_schema

# ==========================================
# 1. DATABASE SETUP
# ==========================================
with engine.connect() as conn:
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
    conn.commit()

# Build the tables
student_model.Base.metadata.drop_all(bind=engine) # <--- THIS WIPES THE DB
student_model.Base.metadata.create_all(bind=engine) # <--- THIS REBUILDS IT WITH NEW COLUMNS

# ==========================================
# 2. FASTAPI APP & MIDDLEWARE
# ==========================================
app = FastAPI(title="Inno Mind Academy API")

origins = [
    "http://localhost:5173",
    "http://localhost:5174",
    "https://inno-mind-academy-learn-n-play.onrender.com", # Your Render frontend URL
    "https://www.innomindacademy.com",                     # NEW: Custom domain with www
    "https://innomindacademy.com"                          # NEW: Custom domain without www
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root_health_check():
    """Confirms the server is awake and running."""
    return {"status": "online", "system": "Inno Mind Academy V1.0 - Season 1 Beta"}

# ==========================================
# 3. AUTHENTICATION & SECURITY
# ==========================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/students/login")

async def get_current_student(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """The Auth Guard: Verifies the JWT passport and retrieves the verified student."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id_str: str = payload.get("sub")
        if student_id_str is None:
            raise credentials_exception
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Passport expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise credentials_exception

    student = db.query(student_model.Student).filter(student_model.Student.student_id == student_id_str).first()
    if student is None:
        raise credentials_exception
        
    return student

# ==========================================
# 4. STUDENT CORE (REGISTER, LOGIN, LEADERBOARD)
# ==========================================
@app.post("/api/v1/students/register", response_model=student_schema.StudentResponse, status_code=status.HTTP_201_CREATED)
async def register_student(student_data: student_schema.StudentCreate, db: Session = Depends(get_db)):
    existing_user = db.query(student_model.Student).filter(
        (student_model.Student.email == student_data.email) |
        (student_model.Student.nickname == student_data.nickname)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="A student with this email or nickname already exists."
        )
    
    hashed_password = get_password_hash(student_data.password)
    
    new_student = student_model.Student(
        email=student_data.email,
        nickname=student_data.nickname,
        password_hash=hashed_password,
        lives_remaining=150,  # Season 1 Beta: Initial Entry Round Buffer
        has_unlimited_lives=False 
    )
    
    db.add(new_student)
    db.commit()
    db.refresh(new_student) 
    
    return new_student

@app.post("/api/v1/students/login")
async def login_student(credentials: student_schema.StudentLogin, db: Session = Depends(get_db)):
    student = db.query(student_model.Student).filter(
        student_model.Student.email == credentials.email
    ).first()
    
    if not student or not verify_password(credentials.password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Incorrect email or password."
        )
    
    access_token = create_access_token(data={"sub": str(student.student_id)})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "student": {
            "student_id": student.student_id,
            "nickname": student.nickname,
            "email": student.email,
            "lives_remaining": student.lives_remaining,
            "trophy_count": student.trophy_count,
            "highest_level_passed": student.highest_level_passed,
            "tier": student.tier.value if hasattr(student.tier, 'value') else student.tier,
            "rating": student.rating
        }
    }

@app.get("/api/v1/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
    top_students = db.query(student_model.Student).order_by(
        student_model.Student.trophy_count.desc()
    ).limit(10).all()
    
    return [{"nickname": student.nickname, "trophies": student.trophy_count} for student in top_students]

# ==========================================
# 5. CONTENT PIPELINE (SANITY)
# ==========================================
# Sanity Config
PROJECT_ID = "qoe3qxct" # Replace with your actual ID
DATASET = "production"
API_VERSION = "v2024-01-01"
SANITY_URL = f"https://{PROJECT_ID}.api.sanity.io/{API_VERSION}/data/query/{DATASET}"

@app.get("/api/v1/questions/fetch-level")
async def get_level_questions_sanity(student_id: str, subject: str, level: int):
    """Fetches questions dynamically from Sanity CMS via REST API."""
    seen_ids = [] # Placeholder for future DB query
    seen_ids_str = json.dumps(seen_ids)
    
    groq_query = f"""
    *[_type == "question" && subject == "{subject}" && level_number == {level} && !(_id in {seen_ids_str})] {{
        _id,
        subject,
        topic,
        level_number,
        question_text,
        "image_url": media.asset->url,
        options,
        correct_answer,
        explanation
    }}
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.get(SANITY_URL, params={"query": groq_query})
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch content from Sanity")
            
        data = response.json()
        
    all_available = data.get("result", [])
    
    if len(all_available) < 30:
        fallback_query = f'*[_type == "question" && subject == "{subject}" && level_number == {level}]'
        async with httpx.AsyncClient() as client:
            fallback_response = await client.get(SANITY_URL, params={"query": fallback_query})
            all_available = fallback_response.json().get("result", [])
            
    selected_questions = random.sample(all_available, min(len(all_available), 30))
    return {"questions": selected_questions}


# ==========================================
# 6. ARENA GAMEPLAY & GRADING
# ==========================================
@app.get("/api/v1/missions")
async def get_available_missions():
    """Returns the active subjects for the Season 1 Beta directly."""
    return [
        "quantitative-aptitude", 
        "general-knowledge", 
        "logical-reasoning"
    ]

class QuizSubmission(BaseModel):
    student_id: UUID
    syllabus_tag: str
    answers: Dict[str, List[str]] # Changed from int to str to support Sanity IDs

@app.post("/api/v1/arena/submit")
async def submit_exam(
    submission: QuizSubmission, 
    db: Session = Depends(get_db),
    current_student: student_model.Student = Depends(get_current_student)
):
    if str(current_student.student_id) != str(submission.student_id):
        raise HTTPException(status_code=403, detail="Unauthorized.")

    # 1. Extract the Sanity Question IDs the student just answered
    question_ids = list(submission.answers.keys())
    if not question_ids:
        raise HTTPException(status_code=400, detail="No answers submitted.")

    question_ids_str = json.dumps(question_ids)

    # 2. Securely fetch ONLY the answer keys for these specific questions from Sanity
    groq_query = f"""
    *[_type == "question" && _id in {question_ids_str}] {{
        _id,
        level_number,
        correct_answer
    }}
    """
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            SANITY_URL,
            params={"query": groq_query}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch answer key from CMS.")
            
        data = response.json()
        
    sanity_questions = data.get("result", [])
    
    if not sanity_questions:
        raise HTTPException(status_code=400, detail="Could not validate exam data.")

    # We pull the level of the quiz to see if it's their new highest level
    quiz_level = sanity_questions[0].get("level_number", 1)
    
    # Map the Sanity correct answers to a dictionary for O(1) instant lookup
    answer_key = {q["_id"]: [q["correct_answer"]] for q in sanity_questions if "correct_answer" in q}

    # 3. Grade the Exam
    correct_count = 0
    total_questions = len(question_ids)

    for q_id, selected_options in submission.answers.items():
        if q_id in answer_key:
            # Sort both arrays just in case, though Sanity answers are single strings mapped to arrays
            if sorted(selected_options) == sorted(answer_key[q_id]):
                correct_count += 1

    current_accuracy = (correct_count / total_questions) * 100
    passed_current = current_accuracy >= 50.0

    # ==========================================
    # 4. PHASE 1: UPDATE LIFETIME STATS
    # ==========================================
    current_student.total_questions_attempted += total_questions
    current_student.total_correct_answers += correct_count
    
    if current_student.total_questions_attempted > 0:
        lifetime_average = (current_student.total_correct_answers / current_student.total_questions_attempted) * 100
    else:
        lifetime_average = 0.0

    if passed_current and quiz_level > current_student.highest_level_passed:
        current_student.highest_level_passed = quiz_level

    # ==========================================
    # 5. PHASE 2: PROCESS DUAL-PATH ECONOMY
    # ==========================================
    message = ""
    if passed_current:
        current_student.trophy_count += 1
        current_student.rating += 10
        message = "Level Cleared! Trophy Awarded."
    else:
        if not current_student.has_unlimited_lives and current_student.lives_remaining > 0:
            current_student.lives_remaining -= 1
            message = "Level Failed. Life Deducted."
        elif current_student.has_unlimited_lives:
            message = "Level Failed. (Infinite Lives Protected You!)"

    # ==========================================
    # 6. PHASE 3: THE MERIT AUTOMATION ENGINE
    # ==========================================
    upgrade_triggered = False
    
    if current_student.tier == student_model.StudentTier.FREEMIUM:
        if lifetime_average >= 70.0 and current_student.highest_level_passed >= 10:
            current_student.tier = student_model.StudentTier.PREMIUM
            message = "🎉 INCREDIBLE! 70%+ Average & Level 10 Cleared. You earned a FREE upgrade to PREMIUM!"
            upgrade_triggered = True
            
    elif current_student.tier == student_model.StudentTier.PREMIUM:
        if lifetime_average >= 90.0 and current_student.highest_level_passed >= 100:
            current_student.tier = student_model.StudentTier.ELITE
            current_student.has_unlimited_lives = True 
            message = "👑 FLAWLESS EXCELLENCE! Welcome to the ELITE tier. Infinite Lives unlocked!"
            upgrade_triggered = True

    db.commit()
    db.refresh(current_student)

    return {
        "score_percentage": round(current_accuracy, 1),
        "correct": correct_count,
        "total": total_questions,
        "passed": passed_current,
        "lives_remaining": current_student.lives_remaining,
        "trophies": current_student.trophy_count,
        "rating": current_student.rating,
        "tier": current_student.tier,
        "lifetime_average": round(lifetime_average, 1),
        "has_unlimited_lives": current_student.has_unlimited_lives,
        "message": message,
        "upgrade_triggered": upgrade_triggered
    }

# ==========================================
# 7. IN-GAME ECONOMY
# ==========================================
@app.post("/api/v1/store/exchange-trophies")
async def exchange_trophies_for_lives(
    current_student: student_model.Student = Depends(get_current_student), 
    db: Session = Depends(get_db)
):
    """Allows students to trade 10 trophies for 20 lives."""
    if current_student.has_unlimited_lives:
        raise HTTPException(status_code=400, detail="You already possess infinite lives.")
    if current_student.trophy_count < 10:
        raise HTTPException(status_code=400, detail="Insufficient balance: 10 Trophies required.")
    
    current_student.trophy_count -= 10
    current_student.lives_remaining += 20  # Updated to match the 10 for 20 rule
    
    db.commit()
    db.refresh(current_student)
    
    return {
        "message": "Refill successful! 20 Lives added.",
        "lives_remaining": current_student.lives_remaining,
        "trophy_count": current_student.trophy_count
    }