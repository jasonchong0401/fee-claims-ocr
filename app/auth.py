"""
认证模块 —— 密码加密、JWT 令牌、权限依赖注入。
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from app.database import get_db
from app.models import Employee

# ── 密码加密 ────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """对明文密码进行 bcrypt 哈希，返回密文存入数据库。"""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否与数据库中的哈希值匹配。"""
    return pwd_context.verify(plain, hashed)


# ── JWT ─────────────────────────────────────────────────
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT 访问令牌。"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT 令牌，返回 payload；校验失败返回 None。"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ── HTTP Bearer 安全方案 ────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


# ── 获取当前用户（所有已登录用户可用） ──────────────────
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Employee:
    """
    从 Authorization: Bearer <token> 中解析当前用户。
    未提供 Token 或 Token 无效时抛出 401。
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = db.query(Employee).filter(
        Employee.username == payload["sub"],
        Employee.is_active == True,
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    return employee


# ── 管理员权限检查 ──────────────────────────────────────
def require_admin(
    current_user: Employee = Depends(get_current_user),
) -> Employee:
    """要求当前用户具有 admin 角色，否则返回 403。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，仅管理员可执行此操作",
        )
    return current_user


# ── 可选认证（未登录也可访问，但登录后提供用户对象） ────
def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[Employee]:
    """不强制登录，但如果提供了有效 Token 则返回用户对象。"""
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None or "sub" not in payload:
        return None
    return db.query(Employee).filter(
        Employee.username == payload["sub"],
        Employee.is_active == True,
    ).first()
