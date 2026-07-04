-- ============================================================
-- 费用报销 OCR 识别系统 —— 数据库初始化脚本
-- 适用: MySQL 5.7+
-- 使用: mysql -u root -p < sql/init.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS fee_claims
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE fee_claims;

CREATE TABLE IF NOT EXISTS receipts (
    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    uuid        VARCHAR(36)  NOT NULL COMMENT '唯一标识符',
    applicant   VARCHAR(50)  DEFAULT NULL COMMENT '报销人姓名/工号',
    expense_type VARCHAR(20) DEFAULT NULL COMMENT '报销类型：交通/餐饮/住宿/办公用品',
    merchant    VARCHAR(100) DEFAULT NULL COMMENT '商户名称',
    total_amount DECIMAL(10,2) DEFAULT NULL COMMENT '费用总额',
    head_count  INT          NOT NULL DEFAULT 1 COMMENT '参与人数',

    image_path  VARCHAR(255) DEFAULT NULL COMMENT '图片相对路径',
    ocr_raw_text TEXT        DEFAULT NULL COMMENT 'OCR原始返回文本（审计用）',

    status      TINYINT      NOT NULL DEFAULT 0 COMMENT '0:待处理, 1:已提取, -1:提取失败',
    error_message TEXT       DEFAULT NULL COMMENT '失败原因',

    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    -- 索引
    UNIQUE INDEX idx_uuid (uuid),
    INDEX idx_applicant (applicant),
    INDEX idx_expense_type (expense_type),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='费用报销记录表';

-- ============================================================
-- 员工用户表
-- ============================================================
CREATE TABLE IF NOT EXISTS employee (
    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    username    VARCHAR(50)  NOT NULL COMMENT '登录用户名',
    employee_id VARCHAR(50)  NOT NULL COMMENT '员工工号',
    role        VARCHAR(20)  NOT NULL DEFAULT 'user' COMMENT '角色: admin/user',
    department  VARCHAR(100) DEFAULT NULL COMMENT '部门',
    email       VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    pass_code   VARCHAR(255) NOT NULL COMMENT '加密后的密码(bcrypt)',
    start_date  DATE         DEFAULT NULL COMMENT '入职日期',
    end_date    DATE         DEFAULT NULL COMMENT '离职日期',
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE COMMENT '是否在职',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE INDEX idx_employee_username (username),
    UNIQUE INDEX idx_employee_id (employee_id),
    INDEX idx_employee_role (role),
    INDEX idx_employee_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工用户表';
