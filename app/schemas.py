"""
Pydantic 校验模型 —— 请求/响应数据结构。
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ══════════════════════════════════════════════════════════
#  费用报销 Receipt
# ══════════════════════════════════════════════════════════

class UploadResponse(BaseModel):
    code: int = 0
    msg: str = "上传成功"
    data: Optional[dict] = None


class ReceiptOut(BaseModel):
    id: int
    uuid: str
    applicant: Optional[str] = None
    expense_type: Optional[str] = None
    merchant: Optional[str] = None
    total_amount: Optional[float] = None
    head_count: int = 1
    image_path: Optional[str] = None
    ocr_raw_text: Optional[str] = None
    status: int = 0
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ReceiptListResponse(BaseModel):
    code: int = 0
    msg: str = "查询成功"
    data: list[ReceiptOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class ReceiptDetailResponse(BaseModel):
    code: int = 0
    msg: str = "查询成功"
    data: Optional[ReceiptOut] = None


class ReceiptUpdate(BaseModel):
    applicant: Optional[str] = None
    expense_type: Optional[str] = None
    merchant: Optional[str] = None
    total_amount: Optional[float] = None
    head_count: Optional[int] = None


class ErrorResponse(BaseModel):
    code: int
    msg: str
    detail: Optional[str] = None


class FileValidationError(ValueError):
    """文件校验失败异常"""
    pass


# ══════════════════════════════════════════════════════════
#  用户管理 Employee
# ══════════════════════════════════════════════════════════

class EmployeeCreate(BaseModel):
    """创建用户（管理员操作）。"""
    username: str = Field(..., min_length=2, max_length=50)
    employee_id: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field(default="user", pattern="^(admin|user)$")
    department: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class EmployeeOut(BaseModel):
    """返回用户信息（不含密码）。"""
    id: int
    username: str
    employee_id: str
    role: str
    department: Optional[str] = None
    email: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class EmployeeListResponse(BaseModel):
    code: int = 0
    msg: str = "查询成功"
    data: list[EmployeeOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class EmployeeDetailResponse(BaseModel):
    code: int = 0
    msg: str = "查询成功"
    data: Optional[EmployeeOut] = None


class EmployeeUpdateSelf(BaseModel):
    """普通用户修改自己的信息（不含敏感字段）。"""
    email: Optional[str] = Field(default=None, max_length=100)
    department: Optional[str] = Field(default=None, max_length=100)


class EmployeeUpdateByAdmin(BaseModel):
    """管理员修改任意用户信息。"""
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    department: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=100)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    """修改密码。"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    """登录请求。"""
    username: str
    password: str


class LoginResponse(BaseModel):
    code: int = 0
    msg: str = "登录成功"
    data: Optional[dict] = None


class GenericResponse(BaseModel):
    code: int = 0
    msg: str = "操作成功"
    data: Optional[dict] = None
