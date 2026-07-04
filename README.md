# 费用报销 OCR 识别系统

基于 Python + FastAPI + MySQL 的企业内部费用报销管理系统。核心流程：

> 上传票据图片 → OCR 提取关键信息 → 结构化数据存入 MySQL → 图片存入本地存储

## 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | FastAPI (自带 OpenAPI 文档) |
| ORM | SQLAlchemy 2.0 |
| 数据库 | MySQL 5.7+ / 8.0 |
| OCR | Mock 实现（可快速替换为百度OCR / 阿里云OCR / PaddleOCR） |
| 环境管理 | python-dotenv |

## 快速开始

### 1. 环境准备

- Python 3.9+
- MySQL 5.7+ (运行中)

### 2. 安装依赖

```bash
cd fee_claims
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 按需编辑 .env 中的数据库密码等配置
```

### 4. 创建数据库

```bash
# 方式一：用 SQL 脚本创建
mysql -u root -p < sql/init.sql

# 方式二：手动创建
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS fee_claims CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 5. 启动服务

```bash
python -m app.main
```

服务启动后访问：
- API 文档 (Swagger): http://localhost:8000/docs
- API 文档 (ReDoc): http://localhost:8000/redoc
- 健康检查: http://localhost:8000/api/health

首次启动会自动建表（SQLAlchemy `create_all`）。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传票据图片（multipart/form-data），返回任务 UUID |
| GET | `/api/receipt/{uuid}` | 根据 UUID 查询单条报销明细 |
| GET | `/api/receipts` | 分页查询，支持按报销人、日期范围、状态筛选 |
| GET | `/api/health` | 健康检查 |

### 筛选参数 (GET /api/receipts)

| 参数 | 类型 | 说明 |
|------|------|------|
| applicant | string | 报销人（模糊匹配） |
| start_date | string | 开始日期 YYYY-MM-DD |
| end_date | string | 结束日期 YYYY-MM-DD |
| status | int | 0=待处理, 1=已提取, -1=失败 |
| page | int | 页码，默认 1 |
| page_size | int | 每页条数，默认 20，最大 100 |

### 使用示例

```bash
# 上传票据
curl -X POST http://localhost:8000/api/upload \
  -F "file=@receipt.jpg"

# 查询单条
curl http://localhost:8000/api/receipt/550e8400-e29b-41d4-a716-446655440000

# 分页查询（按报销人筛选）
curl "http://localhost:8000/api/receipts?applicant=张三&page=1&page_size=10"
```

## 项目结构

```
fee_claims/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 启动文件 + 路由
│   ├── models.py        # SQLAlchemy 数据库模型
│   ├── schemas.py       # Pydantic 请求/响应模型
│   └── ocr_service.py   # OCR 识别服务（Mock）
├── sql/
│   └── init.sql         # MySQL 建库建表脚本
├── uploads/
│   └── receipts/        # 上传图片存储目录
├── config.py            # 全局配置（读取 .env）
├── requirements.txt
├── .env.example
└── README.md
```

## 接入真实 OCR

Mock OCR 在 `app/ocr_service.py` 中。替换步骤：

1. 在 `OCRService.recognize()` 中调用真实 API
2. 从 API 响应中提取文本，填入 `OCRResult` 字段
3. 可选：使用 `extract_amount()` / `extract_applicant()` 等正则函数做后处理

## 文件上传限制

- 仅支持 `.jpg` / `.jpeg` / `.png` 格式
- 单文件大小不超过 5MB
- 文件以 UUID 重命名存储，避免冲突

## 扩展说明 (head_count)

当前 `head_count` 仅存储总人数 (INT, 默认 1)。若未来需记录每人分摊金额，新增 `receipt_splits` 子表即可：

```sql
CREATE TABLE receipt_splits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    receipt_id INT NOT NULL,
    person_name VARCHAR(50),
    split_amount DECIMAL(10,2),
    FOREIGN KEY (receipt_id) REFERENCES receipts(id)
);
```
