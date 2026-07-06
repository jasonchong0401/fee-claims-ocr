"""
FastAPI 启动文件 —— 费用报销 OCR 识别系统（含用户认证）。

启动方式:
    cd fee_claims
    cp .env.example .env
    pip install -r requirements.txt
    python -m app.main
"""

import os
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from config import settings, BASE_DIR
from app.database import engine, SessionLocal, get_db
from app.models import Base, Receipt, Employee
from app.auth import get_current_user, require_admin, hash_password, verify_password, create_access_token
from app.schemas import (
    UploadResponse,
    ReceiptOut,
    ReceiptDetailResponse,
    ReceiptListResponse,
    ReceiptUpdate,
    ApprovalUpdate,
    FileValidationError,
    LoginRequest,
    LoginResponse,
    EmployeeCreate,
    EmployeeOut,
    EmployeeDetailResponse,
)
from app.ocr_service import OCRService
from app.routers.employees import router as employee_router

# ── 日志 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fee_claims")

# ── OCR 服务 ────────────────────────────────────────────
ocr_service = OCRService()


# ── FastAPI 生命周期 ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表已就绪")
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    yield
    engine.dispose()
    logger.info("数据库连接池已释放")


app = FastAPI(
    title="费用报销 OCR 识别系统",
    description="企业内部费用报销管理 API",
    version="1.1.0",
    lifespan=lifespan,
)

# ── 静态文件 ────────────────────────────────────────────
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# ── 注册路由 ────────────────────────────────────────────
app.include_router(employee_router)


# ── 全局异常处理 ────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "msg": exc.detail},
    )


@app.exception_handler(FileValidationError)
async def file_validation_handler(request: Request, exc: FileValidationError):
    return JSONResponse(status_code=400, content={"code": 400, "msg": str(exc)})


@app.exception_handler(OperationalError)
async def db_error_handler(request: Request, exc: OperationalError):
    logger.error(f"数据库异常: {exc}")
    return JSONResponse(status_code=500, content={"code": 500, "msg": "Database error"})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception(f"未处理异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "msg": "Internal server error", "detail": str(exc)},
    )


# ── 工具函数 ────────────────────────────────────────────
def validate_upload_file(file: UploadFile) -> None:
    if not file.filename:
        raise FileValidationError("文件名为空")
    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"不支持的文件类型 .{ext}，仅允许: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}"
        )
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.MAX_FILE_SIZE_BYTES:
        max_mb = settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise FileValidationError(f"文件大小超过 {max_mb}MB 限制")
    if size == 0:
        raise FileValidationError("文件为空")


async def save_upload_file(file: UploadFile, employee_id: str, receipt_uuid: str) -> str:
    """
    保存上传文件至分层目录:
      uploads/receipts/{employee_id}/{YYYY-MM-DD}/{uuid}.{ext}

    返回相对于项目根目录的路径。
    """
    ext = Path(file.filename).suffix
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    sub_dir = Path(settings.UPLOAD_DIR) / employee_id / date_str
    sub_dir.mkdir(parents=True, exist_ok=True)

    new_filename = f"{receipt_uuid}{ext}"
    dest = sub_dir / new_filename

    content = await file.read()
    dest.write_bytes(content)
    relative_path = str(dest)
    logger.info(f"图片已保存: {relative_path} ({len(content)} bytes)")
    return relative_path


# ══════════════════════════════════════════════════════════
#  页面路由
# ══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def login_page():
    """登录页面（入口）"""
    html_path = BASE_DIR / "static" / "login.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Login page not found</h1>", status_code=404)


@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    """上传页面（需登录，前端检查 token）"""
    html_path = BASE_DIR / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Upload page not found</h1>", status_code=404)


@app.get("/api/health", summary="健康检查")
async def health_check():
    return {"code": 0, "msg": "ok"}


# ══════════════════════════════════════════════════════════
#  费用报销 API（需登录）
# ══════════════════════════════════════════════════════════

@app.post(
    "/api/upload",
    response_model=UploadResponse,
    summary="上传票据图片",
    description="接收票据图片，OCR 识别后入库。需登录。",
)
async def upload_receipt(
    file: UploadFile = File(..., description="票据图片文件"),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    validate_upload_file(file)

    # 1. 先创建记录获取 UUID
    receipt = Receipt(
        status=0,
        employee_id=current_user.employee_id,
        approval_status="pending",
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    task_id = receipt.uuid

    # 2. 保存图片到分层目录: {employee_id}/{date}/{uuid}.{ext}
    try:
        image_path = await save_upload_file(
            file,
            employee_id=current_user.employee_id,
            receipt_uuid=task_id,
        )
        receipt.image_path = image_path
        db.commit()
        db.refresh(receipt)
    except Exception as exc:
        logger.exception("图片保存失败")
        raise HTTPException(status_code=500, detail=f"图片保存失败: {exc}")

    try:
        result = ocr_service.recognize(image_path)
        logger.info(f"OCR 结果: {result.to_dict()}")

        if result.total_amount is None or result.total_amount <= 0:
            raise ValueError("金额识别失败，请手动输入")

        # 非 admin 用户：OCR 识别的申请人必须与登录用户一致
        if current_user.role != "admin":
            ocr_applicant = (result.applicant or "").strip()
            if ocr_applicant and ocr_applicant not in (current_user.username, current_user.employee_id):
                raise ValueError(
                    f"票据申请人 '{ocr_applicant}' 与当前用户 '{current_user.username}' 不一致，"
                    f"请联系管理员处理"
                )

        receipt.applicant = result.applicant
        receipt.expense_type = result.expense_type
        receipt.merchant = result.merchant
        receipt.total_amount = result.total_amount
        receipt.head_count = result.head_count or 1
        receipt.ocr_raw_text = result.raw_text
        receipt.status = 1
        db.commit()
        db.refresh(receipt)

        return UploadResponse(
            code=0,
            msg="上传并识别成功",
            data={
                "uuid": task_id,
                "applicant": receipt.applicant,
                "expense_type": receipt.expense_type,
                "merchant": receipt.merchant,
                "total_amount": float(receipt.total_amount),
                "head_count": receipt.head_count,
                "status": receipt.status,
            },
        )

    except ValueError as exc:
        receipt.status = -1
        receipt.error_message = str(exc)
        db.commit()
        return JSONResponse(
            status_code=422,
            content={
                "code": 422, "msg": str(exc),
                "data": {"uuid": task_id, "status": -1},
            },
        )

    except Exception as exc:
        receipt.status = -1
        receipt.error_message = f"OCR 识别异常: {exc}"
        db.commit()
        logger.exception(f"任务 {task_id} OCR 异常")
        return JSONResponse(
            status_code=500,
            content={
                "code": 500, "msg": "OCR 识别失败",
                "data": {"uuid": task_id, "status": -1, "error": str(exc)},
            },
        )


@app.get(
    "/api/receipt/{task_id}",
    response_model=ReceiptDetailResponse,
    summary="查询单条报销明细",
)
async def get_receipt(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    receipt = db.query(Receipt).filter(Receipt.uuid == task_id).first()
    if not receipt:
        return JSONResponse(status_code=404, content={"code": 404, "msg": f"记录不存在: {task_id}"})
    return ReceiptDetailResponse(
        code=0, msg="查询成功",
        data=ReceiptOut.model_validate(receipt.to_dict()),
    )


@app.put(
    "/api/receipt/{task_id}",
    response_model=ReceiptDetailResponse,
    summary="更新报销记录",
)
async def update_receipt(
    task_id: str,
    body: ReceiptUpdate,
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    receipt = db.query(Receipt).filter(Receipt.uuid == task_id).first()
    if not receipt:
        return JSONResponse(status_code=404, content={"code": 404, "msg": f"记录不存在: {task_id}"})

    update_data = body.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(receipt, key, val)
    db.commit()
    db.refresh(receipt)
    return ReceiptDetailResponse(
        code=0, msg="更新成功",
        data=ReceiptOut.model_validate(receipt.to_dict()),
    )


@app.get(
    "/api/receipts",
    response_model=ReceiptListResponse,
    summary="分页查询报销记录",
)
async def list_receipts(
    applicant: Optional[str] = Query(None, description="报销人"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    status: Optional[int] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    query = db.query(Receipt)
    if applicant:
        query = query.filter(Receipt.applicant.contains(applicant))
    if start_date:
        query = query.filter(Receipt.created_at >= f"{start_date} 00:00:00")
    if end_date:
        query = query.filter(Receipt.created_at <= f"{end_date} 23:59:59")
    if status is not None:
        query = query.filter(Receipt.status == status)

    total = query.count()
    records = (
        query.order_by(desc(Receipt.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReceiptListResponse(
        code=0, msg="查询成功",
        data=[ReceiptOut.model_validate(r.to_dict()) for r in records],
        total=total, page=page, page_size=page_size,
    )


# ══════════════════════════════════════════════════════════
#  我的报销（需登录）
# ══════════════════════════════════════════════════════════

@app.get("/admin/review", response_class=HTMLResponse)
async def admin_review_page():
    """审批页面（需管理员权限，前端检查 token + role）"""
    html_path = BASE_DIR / "static" / "admin-review.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Review page not found</h1>", status_code=404)


@app.get("/my-receipts", response_class=HTMLResponse)
async def my_receipts_page():
    """我的报销页面（需登录，前端检查 token）"""
    html_path = BASE_DIR / "static" / "my-receipts.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>My Receipts page not found</h1>", status_code=404)


@app.get(
    "/api/my-receipts",
    response_model=ReceiptListResponse,
    summary="查询当前用户的报销记录",
)
async def list_my_receipts(
    date: Optional[str] = Query(None, description="日期筛选 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """当前登录用户查看自己提交的报销单列表，支持按日期搜索。"""
    query = db.query(Receipt).filter(
        Receipt.employee_id == current_user.employee_id
    )
    if date:
        query = query.filter(Receipt.created_at >= f"{date} 00:00:00")
        query = query.filter(Receipt.created_at <= f"{date} 23:59:59")

    total = query.count()
    records = (
        query.order_by(desc(Receipt.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReceiptListResponse(
        code=0, msg="查询成功",
        data=[ReceiptOut.model_validate(r.to_dict()) for r in records],
        total=total, page=page, page_size=page_size,
    )


@app.get(
    "/api/admin/review-queue",
    response_model=ReceiptListResponse,
    summary="审批队列（管理员）",
)
async def admin_review_queue(
    approval_status: Optional[str] = Query("pending", description="按审批状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    """管理员查看待审批 / 已审批的报销单列表。"""
    query = db.query(Receipt)
    if approval_status:
        query = query.filter(Receipt.approval_status == approval_status)

    total = query.count()
    records = (
        query.order_by(desc(Receipt.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ReceiptListResponse(
        code=0, msg="查询成功",
        data=[ReceiptOut.model_validate(r.to_dict()) for r in records],
        total=total, page=page, page_size=page_size,
    )


@app.put(
    "/api/receipt/{task_id}/approve",
    response_model=ReceiptDetailResponse,
    summary="审批报销单（管理员）",
)
async def approve_receipt(
    task_id: str,
    body: ApprovalUpdate,
    db: Session = Depends(get_db),
    admin: Employee = Depends(require_admin),
):
    """管理员审批报销单：通过 / 拒绝 / 要求修改。"""
    receipt = db.query(Receipt).filter(Receipt.uuid == task_id).first()
    if not receipt:
        return JSONResponse(
            status_code=404, content={"code": 404, "msg": f"记录不存在: {task_id}"},
        )
    receipt.approval_status = body.approval_status
    if body.comment:
        receipt.review_comment = body.comment
    db.commit()
    db.refresh(receipt)
    return ReceiptDetailResponse(
        code=0, msg="审批完成",
        data=ReceiptOut.model_validate(receipt.to_dict()),
    )


# ── 入口 ────────────────────────────────────────────────

# Mount static assets (CSS, JS) — after all routes so routes take priority
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"启动服务: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"API 文档: http://{settings.HOST}:{settings.PORT}/docs")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
