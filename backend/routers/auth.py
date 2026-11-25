"""회원가입 · 로그인 (JWT)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import User, UserFlowState
from backend.schemas import FlowStateBody, LoginRequest, RegisterRequest, TokenResponse, UserOut
from backend.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id), user=UserOut(id=user.id, email=user.email, name=user.name)
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = req.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "이미 가입된 이메일입니다.")
    user = User(email=email, name=req.name.strip() or email.split("@")[0], password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == req.email.lower()))
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email, name=user.name)


@router.get("/me/flow")
def get_flow(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """학습 진행 상태 조회 (새로고침 후 복원용)"""
    row = db.get(UserFlowState, user.id)
    return {"state": row.state if row else None}


@router.put("/me/flow")
def put_flow(body: FlowStateBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(UserFlowState, user.id)
    if row is None:
        row = UserFlowState(user_id=user.id)
        db.add(row)
    row.state = body.state
    db.commit()
    return {"ok": True}
