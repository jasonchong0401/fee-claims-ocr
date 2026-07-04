"""
应用全局配置 —— 通过 .env 文件管理数据库密码等敏感信息。
"""

import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)


class Settings:
    # ── 数据库 ──────────────────────────────────────────
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "fee_claims")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "fee_claims")

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            "?charset=utf8mb4"
        )

    # ── 文件上传 ────────────────────────────────────────
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads/receipts")
    MAX_FILE_SIZE_BYTES: int = int(os.getenv("MAX_FILE_SIZE_MB", "5")) * 1024 * 1024
    ALLOWED_EXTENSIONS: set[str] = {
        ext.strip().lower()
        for ext in os.getenv("ALLOWED_EXTENSIONS", "jpg,png,jpeg").split(",")
        if ext.strip()
    }

    # ── JWT 认证 ────────────────────────────────────────
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    # ── 服务 ────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))


settings = Settings()
