"""
FastAPI 启动文件 —— 费用报销 OCR 识别系统（含用户认证）。

启动方式:
    cd fee_claims
    cp .env.example .env
    pip install -r requirements.txt
    python -m app.main
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from config import settings, BASE_DIR
from app.database import engine
from app.models import Base
from app.schemas import FileValidationError

# ── 日志 ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fee_claims")


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
from app.routers.employees import router as employee_router
from app.routers.pages import router as pages_router
from app.routers.receipts import router as receipts_router

app.include_router(employee_router)
app.include_router(pages_router)
app.include_router(receipts_router)

# Mount static assets (CSS, JS) — after all routes so routes take priority
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# ── 全局异常处理 ────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc):
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


# ── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logger.info(f"启动服务: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"API 文档: http://{settings.HOST}:{settings.PORT}/docs")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
