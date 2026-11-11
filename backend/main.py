"""Learnlytics AI - FastAPI REST API Backend.

Provides standard RESTful API endpoints for the Learnlytics AI platform:
- Health and system status
- Authentication (Admin, Staff, Student)
- Student directory & CRUD
- Aggregate KPIs and screening analytics
- Recommendations engine
- AI Tutor conversational endpoint
"""
import math
import os
import sys
from typing import Any, Dict, List, Optional

# Add parent directory to sys.path so backend can import root modules
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import auth
import database as db
import data_service as ds
import risk_engine as risk
import recommendations as recs_engine
import ai_tutor_service as tutor_svc

# Initialize database schema and demo accounts if needed on startup
db.init_db()
auth.seed_demo_users_if_needed()

app = FastAPI(
    title="Learnlytics AI API",
    description="RESTful API for Learnlytics AI Educational Analytics & Early Warning System",
    version="1.0.0",
)

# Configurable CORS origins
cors_origins_env = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8501")
allowed_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sanitize_for_json(data: Any) -> Any:
    """Recursively convert float NaN/Inf values to None so responses are valid JSON."""
    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(x) for x in data]
    elif isinstance(data, float) and (math.isnan(data) or math.isinf(data)):
        return None
    return data


# ---------------------------------------------------------
# Pydantic Request & Response Models
# ---------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class StudentCreateRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=120)
    department: str = Field(..., min_length=1, max_length=80)
    semester: int = Field(..., ge=1, le=12)
    attendance_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    academic_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    assignment_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    email: Optional[str] = Field(None, max_length=160)
    mentor: Optional[str] = Field(None, max_length=120)


class StudentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    department: Optional[str] = Field(None, min_length=1, max_length=80)
    semester: Optional[int] = Field(None, ge=1, le=12)
    attendance_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    academic_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    assignment_rate: Optional[float] = Field(None, ge=0.0, le=100.0)
    email: Optional[str] = Field(None, max_length=160)
    mentor: Optional[str] = Field(None, max_length=120)


class AITutorChatRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1, max_length=1000)
    language: str = Field("English", max_length=30)
    history: List[Dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------
@app.get("/api/health")
def health_check():
    """Health check endpoint indicating API and database connectivity."""
    db_ok = False
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            db_ok = bool(cur.fetchone())
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "Learnlytics AI API",
        "version": "1.0.0",
        "database_connected": db_ok,
    }


@app.post("/api/auth/login")
def login(req: LoginRequest):
    """Authenticate user with username and password."""
    user, err = auth.authenticate(req.username.strip(), req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err or "Invalid username or password."
        )

    # Return safe user profile without password credentials
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "email": user.get("email"),
        "student_id": user.get("student_id"),
        "staff_department": user.get("staff_department"),
        "must_change_password": bool(user.get("must_change_password")),
    }


@app.get("/api/kpis")
def get_kpis():
    """Return top-level student KPIs and support statistics."""
    df = ds.get_screened_df()
    kpis = ds.compute_kpis(df)
    return sanitize_for_json(kpis)


@app.get("/api/students")
def list_students(
    department: Optional[str] = Query(None),
    semester: Optional[int] = Query(None),
    risk_category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """List screened students with optional filtering."""
    df = ds.get_screened_df()
    filtered = ds.filter_df(
        df,
        search=search or "",
        departments=[department] if department else None,
        semesters=[semester] if semester is not None else None,
        categories=[risk_category] if risk_category else None,
    )
    records = filtered.to_dict(orient="records")
    clean_records = sanitize_for_json(records)
    return {
        "total": len(clean_records),
        "students": clean_records,
    }


@app.get("/api/students/{student_id}")
def get_student_details(student_id: str):
    """Get complete details and risk screening analysis for a single student."""
    student, screening = ds.screen_one(student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )

    return sanitize_for_json({
        "student": student,
        "screening": screening,
    })


@app.post("/api/students", status_code=status.HTTP_201_CREATED)
def create_student(req: StudentCreateRequest):
    """Register a new student record."""
    student_dict = req.model_dump()
    ok, errors = ds.add_student(student_dict)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=errors
        )
    return {"message": "Student created successfully.", "student_id": req.student_id}


@app.put("/api/students/{student_id}")
def update_student(student_id: str, req: StudentUpdateRequest):
    """Update an existing student's metrics and profile."""
    existing = ds.get_student(student_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )

    update_fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update."
        )

    merged = {**existing, **update_fields}
    ok, errors = ds.update_student(student_id, merged)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=errors
        )
    return {"message": "Student updated successfully.", "student_id": student_id}


@app.delete("/api/students/{student_id}")
def delete_student(student_id: str):
    """Delete a student record."""
    deleted = ds.delete_student(student_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )
    return {"message": f"Student '{student_id}' deleted successfully."}


@app.get("/api/students/{student_id}/recommendations")
def get_student_recommendations(student_id: str):
    """Generate rule-based actionable recommendations for a student."""
    recs = ds.get_recommendations_for_student(student_id)
    if not recs:
        student = ds.get_student(student_id)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student '{student_id}' not found."
            )

    return sanitize_for_json({
        "student_id": student_id,
        "recommendations": recs or [],
    })


@app.get("/api/analytics/departments")
def get_department_analytics():
    """Return academic summary aggregated by department."""
    df = ds.get_screened_df()
    summary = ds.department_summary_df(df)
    records = summary.to_dict(orient="records")
    return {"departments": sanitize_for_json(records)}


@app.post("/api/ai-tutor/chat")
def ai_tutor_chat(req: AITutorChatRequest):
    """Submit a question to the Learnlytics AI Tutor on behalf of a student."""
    student = ds.get_student(req.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{req.student_id}' not found."
        )

    user_proxy = {
        "id": 9999,
        "role": "student",
        "student_id": req.student_id,
        "display_name": student.get("name", "Student"),
    }

    success, reply = tutor_svc.call_ai_tutor(
        user=user_proxy,
        student_prompt=req.prompt,
        conversation_history=req.history,
        language=req.language,
    )

    if not success:
        return {
            "success": False,
            "reply": reply,
            "error": reply,
        }

    return {
        "success": True,
        "reply": reply,
    }
