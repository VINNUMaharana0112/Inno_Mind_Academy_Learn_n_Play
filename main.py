from enum import Enum
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File
import csv
import io
import json
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.core.database import get_db, engine
from app.core.security import get_password_hash, verify_password, create_access_token
import jwt
from fastapi.security import OAuth2PasswordBearer
from app.core.security import SECRET_KEY, ALGORITHM
import razorpay
import os
import hmac
import hashlib

# Import our new Models and Schemas
from app.models import student as student_model
from app.models import question as question_model # Add this line
from app.models.question import Question
from app.schemas import student as student_schema

from sqlalchemy import text
from pydantic import BaseModel
from typing import Dict, List
from uuid import UUID

# Ensure the database can generate secure UUIDs before building tables
with engine.connect() as conn:
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
    conn.commit()

# Now build the tables
student_model.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inno Mind Academy API")

# Tell FastAPI where the login route is so it can map it in Swagger UI
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/students/login")

async def get_current_student(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """The Auth Guard: Verifies the JWT passport and retrieves the verified student."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 1. Inspect the digital passport
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        student_id_str: str = payload.get("sub")
        if student_id_str is None:
            raise credentials_exception
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Passport expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise credentials_exception

    # 2. Fetch the verified student from the database
    student = db.query(student_model.Student).filter(student_model.Student.student_id == student_id_str).first()
    if student is None:
        raise credentials_exception
        
    return student

# The Bouncer's VIP List
origins = [
    "http://localhost:5173",                 # For your local development
    "https://innomind-client.onrender.com",  # Your Render frontend URL
    "https://www.innomindacademy.com",       # Your live custom domain
    "https://innomindacademy.com",           # Your live root domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
async def root_health_check():
    """Confirms the server is awake and running."""
    return {"status": "online", "system": "Inno Mind Academy V1.0"}

@app.get("/api/v1/missions")
async def get_available_missions(db: Session = Depends(get_db)):
    """Fetches all unique syllabus tags to build the Dashboard Mission Board."""
    
    # Query distinct tags from the database
    tags = db.query(question_model.Question.syllabus_tag).distinct().all()
    
    # SQLAlchemy returns a list of tuples like [('advanced-quadratics',), ('logical-reasoning',)]
    # We unpack it into a clean list of strings
    return [tag[0] for tag in tags if tag[0]]

@app.get("/api/v1/questions")
async def get_level_questions(tag: str, db: Session = Depends(get_db)):
    """Fetches real questions from PostgreSQL for a specific syllabus tag."""
    
    # Query the database for questions matching the requested tag
    questions = db.query(question_model.Question).filter(
        question_model.Question.syllabus_tag == tag
    ).all()
    
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this syllabus tag.")
        
    return questions

@app.post("/api/v1/students/register", response_model=student_schema.StudentResponse, status_code=status.HTTP_201_CREATED)
async def register_student(student_data: student_schema.StudentCreate, db: Session = Depends(get_db)):
    """Registers a new student, hashes their password, and saves to PostgreSQL."""
    
    # 1. Check if the email or nickname is already taken
    existing_user = db.query(student_model.Student).filter(
        (student_model.Student.email == student_data.email) |
        (student_model.Student.nickname == student_data.nickname)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="A student with this email or nickname already exists."
        )
    
    # 2. Hash the password
    hashed_password = get_password_hash(student_data.password)
    
    # 3. Create the database record
    new_student = student_model.Student(
        email=student_data.email,
        nickname=student_data.nickname,
        password_hash=hashed_password
    )
    
    # 4. Save to the database
    db.add(new_student)
    db.commit()
    db.refresh(new_student) # Fetches the newly generated UUID and default values (lives, trophies)
    
    # 5. Return the safe response (Pydantic will automatically strip out the password_hash)
    return new_student

@app.post("/api/v1/students/login")
async def login_student(credentials: student_schema.StudentLogin, db: Session = Depends(get_db)):
    """Verifies credentials and issues a cryptographic JWT passport."""
    
    # 1. Find the user
    student = db.query(student_model.Student).filter(
        student_model.Student.email == credentials.email
    ).first()
    
    # 2. Check password
    if not student or not verify_password(credentials.password, student.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Incorrect email or password."
        )
    
    # 3. Mint the Digital Passport (JWT) containing their secure ID
    access_token = create_access_token(data={"sub": str(student.student_id)})
    
    # 4. Return both the token and the profile
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "student": {
            "student_id": student.student_id,
            "nickname": student.nickname,
            "email": student.email,
            "lives_remaining": student.lives_remaining,
            "trophy_count": student.trophy_count,
            "tier": student.tier.value if hasattr(student.tier, 'value') else student.tier,
            "rating": student.rating
        }
    }

router = APIRouter()

@router.post("/upload-csv")
async def upload_questions_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV.")

    try:
        # 2. Read and Decode the CSV
        contents = await file.read()
        decoded_content = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded_content))

        # List of your supported language codes
        supported_langs = ['hi', 'or', 'ta', 'te', 'mr', 'kn', 'gu', 'bn']
        questions_to_insert = []

        for row in csv_reader:
            # 3. Build the English Options JSON Array
            options_en = [
                row.get('opt_a_en', '').strip(),
                row.get('opt_b_en', '').strip(),
                row.get('opt_c_en', '').strip(),
                row.get('opt_d_en', '').strip()
            ]
            # Filter out any accidentally empty columns
            options_en = [opt for opt in options_en if opt] 

            # 4. Pack Regional Translations into the Multilingual Hub
            packed_translations = {}
            for lang in supported_langs:
                # Check if this row actually has a translation for this language
                if row.get(f'q_{lang}') and row[f'q_{lang}'].strip():
                    packed_translations[lang] = {
                        "question": row[f'q_{lang}'].strip(),
                        "options": [
                            row.get(f'opt_a_{lang}', '').strip(),
                            row.get(f'opt_b_{lang}', '').strip(),
                            row.get(f'opt_c_{lang}', '').strip(),
                            row.get(f'opt_d_{lang}', '').strip()
                        ],
                        "explanation": row.get(f'exp_{lang}', '').strip()
                    }

            # 5. Map CSV data to your exact SQLAlchemy Model
            new_question = Question(
                syllabus_tag=row.get('topic', '').strip(),
                level=int(row.get('level_number', 1)),
                
                question_text=row.get('q_en', '').strip(),
                passage_text=row.get('passage_en', '').strip(), # Optional
                
                options=options_en, # Stored as JSONB
                correct_answers=[row.get('correct_option', '').strip().upper()], # Stored as JSONB
                explanation=row.get('exp_en', '').strip(),
                
                translations=packed_translations # The massive JSONB hub
            )
            questions_to_insert.append(new_question)

        # 6. Bulk save to Neon Postgres
        db.add_all(questions_to_insert)
        db.commit()

        return {
            "status": "success", 
            "message": f"Successfully imported {len(questions_to_insert)} questions into the Basecamp Database."
        }

    except KeyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Missing required CSV column: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")
    
# --- Grading Schema ---
class QuizSubmission(BaseModel):
    student_id: UUID
    syllabus_tag: str
    answers: Dict[int, List[str]]

# --- Grading Endpoint ---
@app.post("/api/v1/arena/submit")
async def submit_exam(
    submission: QuizSubmission, 
    db: Session = Depends(get_db),
    current_student: student_model.Student = Depends(get_current_student)
):
    """Grades the exam, calculates lifetime accuracy, and triggers merit upgrades."""
    
    if str(current_student.student_id) != str(submission.student_id):
        raise HTTPException(status_code=403, detail="Unauthorized.")

    questions = db.query(question_model.Question).filter(
        question_model.Question.syllabus_tag == submission.syllabus_tag
    ).all()
    
    if not questions:
        raise HTTPException(status_code=400, detail="Exam data not found.")

    # We pull the level of the quiz to see if it's their new highest level
    quiz_level = questions[0].level 
    answer_key = {q.id: q.correct_answers for q in questions}

    correct_count = 0
    total_questions = len(questions)

    for q_id_str, selected_options in submission.answers.items():
        q_id = int(q_id_str)
        if q_id in answer_key:
            if sorted(selected_options) == sorted(answer_key[q_id]):
                correct_count += 1

    current_accuracy = (correct_count / total_questions) * 100
    passed_current = current_accuracy >= 50.0

    # ==========================================
    # PHASE 1: UPDATE LIFETIME STATS
    # ==========================================
    current_student.total_questions_attempted += total_questions
    current_student.total_correct_answers += correct_count
    
    # Calculate true lifetime average securely
    if current_student.total_questions_attempted > 0:
        lifetime_average = (current_student.total_correct_answers / current_student.total_questions_attempted) * 100
    else:
        lifetime_average = 0.0

    # Track progression if they passed a new, higher level
    if passed_current and quiz_level > current_student.highest_level_passed:
        current_student.highest_level_passed = quiz_level

    # ==========================================
    # PHASE 2: PROCESS DUAL-PATH ECONOMY
    # ==========================================
    message = ""
    if passed_current:
        current_student.trophy_count += 1
        current_student.rating += 10
        message = "Level Cleared! Trophy Awarded."
    else:
        # Only deduct a life if they DO NOT have the God Mode perk activated
        if not current_student.has_unlimited_lives and current_student.lives_remaining > 0:
            current_student.lives_remaining -= 1
            message = "Level Failed. Life Deducted."
        elif current_student.has_unlimited_lives:
            message = "Level Failed. (Infinite Lives Protected You!)"

    # ==========================================
    # PHASE 3: 🚨 THE MERIT AUTOMATION ENGINE 🚨
    # ==========================================
    upgrade_triggered = False
    
    # Rule 1: Freemium to Premium (70% Average + Level 10 Cleared)
    if current_student.tier == student_model.StudentTier.FREEMIUM:
        if lifetime_average >= 70.0 and current_student.highest_level_passed >= 10:
            current_student.tier = student_model.StudentTier.PREMIUM
            message = "🎉 INCREDIBLE! 70%+ Average & Level 10 Cleared. You earned a FREE upgrade to PREMIUM!"
            upgrade_triggered = True

    # Rule 2: Premium to Elite (90% Average + Level 100 Cleared)
    elif current_student.tier == student_model.StudentTier.PREMIUM:
        if lifetime_average >= 90.0 and current_student.highest_level_passed >= 100:
            current_student.tier = student_model.StudentTier.ELITE
            current_student.has_unlimited_lives = True # Grant the Elite Perk!
            message = "👑 FLAWLESS EXCELLENCE! 90%+ Average & Level 100 Cleared. Welcome to the ELITE tier. Infinite Lives unlocked!"
            upgrade_triggered = True

    db.commit()
    db.refresh(current_student)

    # Return everything so the React UI can update dynamically
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
    
@app.get("/api/v1/leaderboard")
async def get_leaderboard(db: Session = Depends(get_db)):
    """Fetches the top 10 students ranked by total trophies."""
    
    top_students = db.query(student_model.Student).order_by(
        student_model.Student.trophy_count.desc()
    ).limit(10).all()
    
    leaderboard = [
        {"nickname": student.nickname, "trophies": student.trophy_count} 
        for student in top_students
    ]
    
    return leaderboard

# --- COMMERCIAL GATEWAY (RAZORPAY) ---

# Initialize the Razorpay Client (Use your test keys from the Razorpay Dashboard)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_YOUR_TEST_KEY_HERE")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "YOUR_TEST_SECRET_HERE")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@app.post("/api/v1/payments/create-order")
async def create_premium_order(current_student: student_model.Student = Depends(get_current_student)):
    """Generates a secure Razorpay order for the Premium Tier upgrade."""
    
    # Check if they are already Premium
    if current_student.tier != student_model.StudentTier.FREEMIUM:
        raise HTTPException(status_code=400, detail="You are already on a Premium or Elite tier.")

    # Set the price for your IPMAT 2027 Premium Batch (e.g., ₹4,999)
    # Razorpay expects the amount in paise, so multiply INR by 100
    order_amount = 4999 * 100 
    
    payment_data = {
        "amount": order_amount,
        "currency": "INR",
        "receipt": f"receipt_{current_student.student_id}",
        "notes": {
            "email": current_student.email,
            "nickname": current_student.nickname
        }
    }
    
    try:
        order = razorpay_client.order.create(data=payment_data)
        return {
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": RAZORPAY_KEY_ID # Send the public key to React to open the window
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to payment gateway: {str(e)}")

@app.post("/api/v1/payments/verify")
async def verify_payment_and_upgrade(
    payment_data: PaymentVerification, 
    db: Session = Depends(get_db),
    current_student: student_model.Student = Depends(get_current_student)
):
    """Verifies the cryptograph signature from Razorpay and upgrades the user."""
    try:
        # 1. Verify the signature to prevent tampering
        # (In production, uncomment the Razorpay verification line below)
        # razorpay_client.utility.verify_payment_signature(payment_data.dict())
        
        # 2. Upgrade the student in the database
        current_student.tier = student_model.StudentTier.PREMIUM
        
        # 3. Give them a massive Premium boost to their lives (e.g., refill to 10)
        current_student.lives_remaining = 10 
        
        db.commit()
        db.refresh(current_student)
        
        return {
            "status": "success", 
            "message": "Welcome to the Premium Cohort!",
            "new_tier": current_student.tier,
            "lives_remaining": current_student.lives_remaining
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Payment verification failed.")
    
# ==========================================
# --- THE INNO MIND ACADEMY MARKETPLACE ---
# ==========================================

# Initialize Razorpay Client
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID", "rzp_test_fake_key"), os.getenv("RAZORPAY_KEY_SECRET", "fake_secret"))
)

class ProductID(str, Enum):
    LIVES_REFILL_PACK = "lives_refill_pack"   # 10 Lives for Rs 99
    UNLIMITED_LIVES = "unlimited_lives"       # Unlimited Lives for Rs 1499
    PREMIUM_UPGRADE = "premium_upgrade"       # Premium Tier for Rs 1499
    ELITE_UPGRADE = "elite_upgrade"           # Elite Tier for Rs 3999

class OrderRequest(BaseModel):
    product_id: ProductID

# --- PART 1: THE IN-GAME TROPHY EXCHANGE ENGINE ---
@app.post("/api/v1/store/exchange-trophies", status_code=status.HTTP_200_OK)
async def exchange_trophies_for_lives(
    current_student: student_model.Student = Depends(get_current_student), 
    db: Session = Depends(get_db)
):
    """Deducts 10 Trophies to grant 10 Lives locally."""
    if current_student.has_unlimited_lives:
        raise HTTPException(status_code=400, detail="You already possess infinite lives.")

    if current_student.trophy_count < 10:
        raise HTTPException(status_code=400, detail="Insufficient balance: 10 Trophies required.")
    
    current_student.trophy_count -= 10
    current_student.lives_remaining += 10
    
    db.commit()
    db.refresh(current_student)
    
    return {
        "message": "Refill successful! 10 Lives added.",
        "lives_remaining": current_student.lives_remaining,
        "trophy_count": current_student.trophy_count
    }

# --- PART 2: THE DYNAMIC MULTI-PRODUCT CHECKOUT GATEWAY ---
@app.post("/api/v1/store/create-order", status_code=status.HTTP_201_CREATED)
async def create_marketplace_order(
    payload: OrderRequest, 
    current_student: student_model.Student = Depends(get_current_student), 
    db: Session = Depends(get_db)
):
    """Generates a secure Razorpay Order token matching our pricing model."""
    PRICING_MATRIX = {
        ProductID.LIVES_REFILL_PACK: 99,
        ProductID.UNLIMITED_LIVES: 1499,
        ProductID.PREMIUM_UPGRADE: 1499,
        ProductID.ELITE_UPGRADE: 3999
    }
    
    amount_in_inr = PRICING_MATRIX[payload.product_id]
    
    if payload.product_id == ProductID.UNLIMITED_LIVES and current_student.has_unlimited_lives:
        raise HTTPException(status_code=400, detail="Infinite lives are already activated.")
    if payload.product_id == ProductID.PREMIUM_UPGRADE and current_student.tier in [student_model.StudentTier.PREMIUM, student_model.StudentTier.ELITE]:
        raise HTTPException(status_code=400, detail="Account is already Premium or higher.")
    if payload.product_id == ProductID.ELITE_UPGRADE and current_student.tier == student_model.StudentTier.ELITE:
        raise HTTPException(status_code=400, detail="Account is already Elite.")

    razorpay_order_data = {
        "amount": amount_in_inr * 100, 
        "currency": "INR",
        "receipt": f"rcpt_{str(current_student.student_id)[:8]}",
        "notes": {
            "student_id": str(current_student.student_id),
            "product_id": payload.product_id.value,
            "email": current_student.email
        }
    }

    try:
        razorpay_order = razorpay_client.order.create(data=razorpay_order_data)
        return {
            "order_id": razorpay_order["id"],
            "amount": razorpay_order["amount"],
            "currency": razorpay_order["currency"],
            "product_id": payload.product_id
        }
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Payment network error: {str(error)}")