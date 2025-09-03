"""
A-View: LibreOffice 기반 문서 뷰어 서비스
AssetERP의 문서 뷰어로 사용되며, 외부 URL의 Office 문서를 PDF로 변환하여 표시
"""

import os
from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logger import get_logger
from config import settings
logger = get_logger(__name__)


from utils import (
    check_libreoffice,
    cleanup_old_cache_files
)

# FastAPI 앱 초기화
app = FastAPI(
    title="A-View Document Processor",
    description="LibreOffice 기반 문서 처리 및 뷰어 서비스",
    version="1.0.0"
)

# 디렉토리 설정
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Redis 연결 설정
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    decode_responses=True
)

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화 작업"""
    logger.info(f"🚀 {settings.APP_NAME} v{settings.VERSION} 시작")
    logger.info(f"📁 캐시 디렉토리: {settings.CACHE_DIR}")
    logger.info(f"🔧 LibreOffice 상태: {'✅ OK' if check_libreoffice() else '❌ ERROR'}")
    
    if redis_client:
        try:
            redis_client.ping()
            logger.info("📦 Redis 연결: ✅ OK")
        except Exception as e:
            logger.error(f"📦 Redis 연결 실패: {e}")
    else:
        logger.warning("📦 Redis: ❌ 비활성화")

@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리 작업"""
    logger.info(f"🛑 {settings.APP_NAME} 종료")
    try:
        cleanup_old_cache_files(24)
        logger.info("캐시 정리 완료")
    except Exception as e:
        logger.error(f"캐시 정리 실패: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=True
    )