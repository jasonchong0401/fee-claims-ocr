"""
报销单路由 —— 上传、查询、更新、列表、我的报销、审批。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, Receipt
from app.auth import get_current_user, require_admin
from app.ocr_service import OCRService
from app.utils import validate_upload_file, save_upload_file
from app.schemas import (
    ApprovalUpdate,
    ReceiptDetailResponse,
    ReceiptListResponse,
    ReceiptOut,
    ReceiptUpdate,
    UploadResponse,
)

logger = logging.getLogger("fee_claims")

# ── OCR 服务 ────────────────────────────────────────────
ocr_service = OCRService()

router = APIRouter(prefix="/api", tags=["报销管理"])


# ── 上传票据 ────────────────────────────────────────────
@router.post(
    "/upload",
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

    # 2. 保存图片到分层目录
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


# ── 查询单条报销 ────────────────────────────────────────
@router.get(
    "/receipt/{task_id}",
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


# ── 更新报销记录 ────────────────────────────────────────
@router.put(
    "/receipt/{task_id}",
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


# ── 分页查询报销记录 ────────────────────────────────────
@router.get(
    "/receipts",
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


# ── 我的报销 ────────────────────────────────────────────
@router.get(
    "/my-receipts",
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


# ── 审批队列（管理员） ──────────────────────────────────
@router.get(
    "/admin/review-queue",
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


# ── 审批报销单（管理员） ────────────────────────────────
@router.put(
    "/receipt/{task_id}/approve",
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
