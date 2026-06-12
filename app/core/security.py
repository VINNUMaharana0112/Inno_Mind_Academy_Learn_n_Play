import os
from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security Keys (In production, never share this secret key)
SECRET_KEY = os.getenv("SECRET_KEY", "inno-mind-academy-super-secret-key-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # Passports expire after 1 week

def get_password_hash(password: str) -> str:
    """Takes a plain text password and returns a secure hash."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a provided password matches the database hash."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    """Generates a cryptographically signed JWT passport."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    # Sign the token using our secret key
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt