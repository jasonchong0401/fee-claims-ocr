"""
SQLAlchemy 数据库模型 —— receipts + employee 表。
"""

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    DECIMAL,
    SmallInteger,
    Date,
    Boolean,
    Index,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# ── Employee 用户表 ─────────────────────────────────────
class Employee(Base):
    __tablename__ = "employee"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增主键")
    username = Column(String(50), unique=True, nullable=False, comment="登录用户名")
    employee_id = Column(
        String(50), unique=True, nullable=False, comment="员工工号"
    )
    role = Column(
        String(20), nullable=False, default="user",
        comment="角色: admin / user"
    )
    department = Column(String(100), nullable=True, comment="部门")
    email = Column(String(100), nullable=True, comment="邮箱")
    pass_code = Column(
        String(255), nullable=False, comment="加密后的密码"
    )
    start_date = Column(Date, nullable=True, comment="入职日期")
    end_date = Column(Date, nullable=True, comment="离职日期")
    is_active = Column(
        Boolean, default=True, nullable=False, comment="是否在职"
    )
    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_employee_username", "username", unique=True),
        Index("idx_employee_id", "employee_id", unique=True),
        Index("idx_employee_role", "role"),
        Index("idx_employee_department", "department"),
    )

    def to_dict(self, include_sensitive: bool = False) -> dict:
        data = {
            "id": self.id,
            "username": self.username,
            "employee_id": self.employee_id,
            "role": self.role,
            "department": self.department,
            "email": self.email,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_sensitive:
            data["pass_code"] = self.pass_code
        return data


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="自增主键")
    uuid = Column(
        String(36),
        unique=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
        comment="唯一标识符",
    )
    applicant = Column(String(50), nullable=True, comment="报销人姓名/工号")
    expense_type = Column(
        String(20), nullable=True, comment="报销类型：交通/餐饮/住宿/办公用品"
    )
    merchant = Column(String(100), nullable=True, comment="商户名称")
    total_amount = Column(DECIMAL(10, 2), nullable=True, comment="费用总额")
    head_count = Column(Integer, default=1, nullable=False, comment="参与人数")

    image_path = Column(String(255), nullable=True, comment="图片相对路径")
    ocr_raw_text = Column(Text, nullable=True, comment="OCR 原始返回文本（审计用）")

    status = Column(
        SmallInteger,
        default=0,
        nullable=False,
        comment="0:待处理, 1:已提取, -1:提取失败",
    )
    error_message = Column(Text, nullable=True, comment="失败原因")

    employee_id = Column(String(50), nullable=True, comment="提交人工号")
    approval_status = Column(
        String(20), default="pending", nullable=False,
        comment="审批状态: pending/approved/rejected/pending_update",
    )
    review_comment = Column(Text, nullable=True, comment="审批意见")

    created_at = Column(
        DateTime, default=datetime.utcnow, nullable=False, comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="更新时间",
    )

    # 常用查询索引
    __table_args__ = (
        Index("idx_applicant", "applicant"),
        Index("idx_expense_type", "expense_type"),
        Index("idx_status", "status"),
        Index("idx_created_at", "created_at"),
        Index("idx_uuid", "uuid", unique=True),
        Index("idx_employee_id", "employee_id"),
        Index("idx_approval_status", "approval_status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "uuid": self.uuid,
            "applicant": self.applicant,
            "expense_type": self.expense_type,
            "merchant": self.merchant,
            "total_amount": float(self.total_amount) if self.total_amount else None,
            "head_count": self.head_count,
            "image_path": self.image_path,
            "ocr_raw_text": self.ocr_raw_text,
            "status": self.status,
            "error_message": self.error_message,
            "employee_id": self.employee_id,
            "approval_status": self.approval_status,
            "review_comment": self.review_comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
