"""
页面路由 —— 前端 HTML 页面 + 健康检查。
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import BASE_DIR

router = APIRouter(tags=["页面"])


@router.get("/", response_class=HTMLResponse)
async def login_page():
    """登录页面（入口）"""
    html_path = BASE_DIR / "static" / "login.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Login page not found</h1>", status_code=404)


@router.get("/upload", response_class=HTMLResponse)
async def upload_page():
    """上传页面（需登录，前端检查 token）"""
    html_path = BASE_DIR / "static" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Upload page not found</h1>", status_code=404)


@router.get("/admin/review", response_class=HTMLResponse)
async def admin_review_page():
    """审批页面（需管理员权限，前端检查 token + role）"""
    html_path = BASE_DIR / "static" / "admin-review.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Review page not found</h1>", status_code=404)


@router.get("/my-receipts", response_class=HTMLResponse)
async def my_receipts_page():
    """我的报销页面（需登录，前端检查 token）"""
    html_path = BASE_DIR / "static" / "my-receipts.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>My Receipts page not found</h1>", status_code=404)


@router.get("/api/health", summary="健康检查")
async def health_check():
    return {"code": 0, "msg": "ok"}
