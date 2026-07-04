"""
用户管理路由 —— 登录、创建用户、修改信息、修改密码。
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
)
from app.schemas import (
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdateSelf,
    EmployeeUpdateByAdmin,
    PasswordChange,
    LoginRequest,
    LoginResponse,
    EmployeeDetailResponse,
    EmployeeListResponse,
    GenericResponse,
)

router = APIRouter(prefix="/api", tags=["用户管理"])


# ── 登录 ────────────────────────────────────────────────
@router.post("/login", response_model=LoginResponse, summary="用户登录")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(
        Employee.username == body.username,
        Employee.is_active == True,
    ).first()

    if not employee or not verify_password(body.password, employee.pass_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token(data={
        "sub": employee.username,
        "role": employee.role,
    })

    return LoginResponse(
        code=0,
        msg="登录成功",
        data={
            "access_token": token,
            "token_type": "bearer",
            "username": employee.username,
            "role": employee.role,
        },
    )


# ── 注册第一个用户（自动成为 admin） ────────────────────
@router.post(
    "/register",
    response_model=EmployeeDetailResponse,
    summary="注册用户",
    description="系统中无用户时，第一个注册的用户自动成为 admin。之后仅 admin 可以创建新用户。",
)
def register_user(body: EmployeeCreate, db: Session = Depends(get_db)):
    # 检查是否已有用户
    existing_count = db.query(Employee).count()

    if existing_count == 0:
        # 第一个用户强制为 admin
        body.role = "admin"
        is_first = True
    else:
        is_first = False

    # 非首个用户需要验证：检查 username / employee_id 是否重复
    if db.query(Employee).filter(Employee.username == body.username).first():
        raise HTTPException(status_code=400, detail=f"用户名 '{body.username}' 已存在")
    if db.query(Employee).filter(Employee.employee_id == body.employee_id).first():
        raise HTTPException(status_code=400, detail=f"工号 '{body.employee_id}' 已存在")

    employee = Employee(
        username=body.username,
        employee_id=body.employee_id,
        role=body.role,
        department=body.department,
        email=body.email,
        pass_code=hash_password(body.password),
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return EmployeeDetailResponse(
        code=0,
        msg="注册成功（首位用户自动成为管理员）" if is_first else "用户创建成功",
        data=EmployeeOut.model_validate(employee.to_dict()),
    )


# ── 创建用户（仅 admin） ─────────────────────────────────
@router.post(
    "/employees",
    response_model=EmployeeDetailResponse,
    summary="管理员创建用户",
)
def create_employee(
    body: EmployeeCreate,
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    if db.query(Employee).filter(Employee.username == body.username).first():
        raise HTTPException(status_code=400, detail=f"用户名 '{body.username}' 已存在")
    if db.query(Employee).filter(Employee.employee_id == body.employee_id).first():
        raise HTTPException(status_code=400, detail=f"工号 '{body.employee_id}' 已存在")

    employee = Employee(
        username=body.username,
        employee_id=body.employee_id,
        role=body.role,
        department=body.department,
        email=body.email,
        pass_code=hash_password(body.password),
        start_date=body.start_date,
        end_date=body.end_date,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return EmployeeDetailResponse(
        code=0,
        msg="用户创建成功",
        data=EmployeeOut.model_validate(employee.to_dict()),
    )


# ── 查看所有用户（仅 admin） ─────────────────────────────
@router.get(
    "/employees",
    response_model=EmployeeListResponse,
    summary="用户列表（管理员）",
)
def list_employees(
    role: Optional[str] = Query(None, description="按角色筛选 admin/user"),
    department: Optional[str] = Query(None, description="按部门筛选"),
    is_active: Optional[bool] = Query(None, description="是否在职"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    query = db.query(Employee)
    if role:
        query = query.filter(Employee.role == role)
    if department:
        query = query.filter(Employee.department.contains(department))
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)

    total = query.count()
    records = (
        query.order_by(Employee.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return EmployeeListResponse(
        code=0,
        msg="查询成功",
        data=[EmployeeOut.model_validate(r.to_dict()) for r in records],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 查看个人信息（所有已登录用户） ──────────────────────
@router.get(
    "/me",
    response_model=EmployeeDetailResponse,
    summary="查看个人信息",
)
def get_my_info(current_user: Employee = Depends(get_current_user)):
    return EmployeeDetailResponse(
        code=0,
        msg="查询成功",
        data=EmployeeOut.model_validate(current_user.to_dict()),
    )


# ── 查看单个用户（仅 admin） ─────────────────────────────
@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeDetailResponse,
    summary="查看指定用户信息（管理员）",
)
def get_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="用户不存在")
    return EmployeeDetailResponse(
        code=0,
        msg="查询成功",
        data=EmployeeOut.model_validate(emp.to_dict()),
    )


# ── 修改个人信息（所有已登录用户） ──────────────────────
@router.put(
    "/me",
    response_model=EmployeeDetailResponse,
    summary="修改个人信息",
    description="修改 email、department 等基本字段。role/start_date/end_date 仅管理员可修改。",
)
def update_my_info(
    body: EmployeeUpdateSelf,
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.email is not None:
        current_user.email = body.email
    if body.department is not None:
        current_user.department = body.department
    db.commit()
    db.refresh(current_user)
    return EmployeeDetailResponse(
        code=0,
        msg="个人信息更新成功",
        data=EmployeeOut.model_validate(current_user.to_dict()),
    )


# ── 修改密码（所有已登录用户） ──────────────────────────
@router.put(
    "/me/password",
    response_model=GenericResponse,
    summary="修改个人密码",
)
def change_my_password(
    body: PasswordChange,
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.old_password, current_user.pass_code):
        raise HTTPException(status_code=400, detail="旧密码不正确")

    current_user.pass_code = hash_password(body.new_password)
    db.commit()
    return GenericResponse(code=0, msg="密码修改成功")


# ── 管理员修改指定用户（含敏感字段） ────────────────────
@router.put(
    "/employees/{employee_id}",
    response_model=EmployeeDetailResponse,
    summary="管理员修改用户信息",
    description="可修改 role、department、email、start_date、end_date、is_active。",
)
def update_employee_by_admin(
    employee_id: int,
    body: EmployeeUpdateByAdmin,
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(emp, key, val)
    db.commit()
    db.refresh(emp)
    return EmployeeDetailResponse(
        code=0,
        msg="用户信息更新成功",
        data=EmployeeOut.model_validate(emp.to_dict()),
    )
