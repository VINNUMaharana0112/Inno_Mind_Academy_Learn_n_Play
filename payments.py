import razorpay
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import os

router = APIRouter()

# Initialize Razorpay Client using Environment Variables
# NEVER hardcode these in your source code!
razorpay_client = razorpay.Client(
    auth=(os.getenv("RAZORPAY_KEY_ID"), os.getenv("RAZORPAY_KEY_SECRET"))
)

class OrderRequest(BaseModel):
    target_tier: str
    student_id: str

class VerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    student_id: str
    target_tier: str

@router.post("/api/v1/payments/create-order")
async def create_order(request: OrderRequest):
    # Set pricing: Expert is ₹499, Genius is ₹999 (Amount is in Paise, so multiply by 100)
    amount = 49900 if request.target_tier == "Expert" else 99900

    order_data = {
        "amount": amount,
        "currency": "INR",
        "receipt": f"receipt_{request.student_id}",
        "notes": {"tier": request.target_tier}
    }
    
    try:
        order = razorpay_client.order.create(data=order_data)
        return {"order_id": order["id"], "amount": amount, "currency": "INR"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/v1/payments/verify")
async def verify_payment(request: VerifyRequest):
    try:
        # 1. Verify the cryptographic signature
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': request.razorpay_order_id,
            'razorpay_payment_id': request.razorpay_payment_id,
            'razorpay_signature': request.razorpay_signature
        })
        
        # 2. SUCCESS! Update the database here.
        # db_student = db.query(Student).filter(Student.student_id == request.student_id).first()
        # db_student.tier = request.target_tier
        # db_student.lives_remaining = 300 if request.target_tier == "Expert" else 400
        # db.commit()
        
        return {"status": "success", "message": f"{request.target_tier} Unlocked!"}
        
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Payment verification failed")