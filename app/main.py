"""
A-View: LibreOffice 기반 문서 뷰어 서비스
AssetERP의 문서 뷰어로 사용되며, 외부 URL의 Office 문서를 PDF로 변환하여 표시
"""

from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from core.logger import get_logger
from core.config import settings

from endpoints.home_routes import router as home_router
from endpoints.aview_routes import router as aview_router
from endpoints.cache_routes import router as cache_router

from core.utils import (
    check_libreoffice,
    cleanup_old_cache_files
)

logger = get_logger(__name__)

def create_app() -> FastAPI:
    app = FastAPI(
        title="A-View Document Viewer for AssetERP",
        description="Document viewer for AssetERP",
        version=settings.VERSION,
    )
    add_routes(app)
    add_statics(app)
    add_events(app)
    return app

def add_statics(app: FastAPI):  
    # 디렉토리 설정
    BASE_DIR = Path(__file__).parent
    STATIC_DIR = BASE_DIR / "static"
    # 정적 파일 마운트
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def add_routes(app: FastAPI):
    app.include_router(home_router)
    app.include_router(aview_router, prefix="/aview", tags=["aview"])
    app.include_router(cache_router, prefix="/cache", tags=["cache"])

def add_events(app: FastAPI):
    app.add_event_handler("startup", lambda: startup_event(app))
    app.add_event_handler("shutdown", shutdown_event)

def startup_event(app: FastAPI):
    """애플리케이션 시작 시 초기화 작업"""
    logger.info("------------------------------------------------")
    logger.info(f"✳️ 시작: {settings.APP_NAME} v{settings.VERSION}")
    logger.info("------------------------------------------------")
    logger.info(f"✔️ HOST: {settings.HOST} - PORT: {settings.PORT}")
    logger.info(f"✔️ 디버그 모드: {'✅ 활성화' if settings.DEBUG else '❌ 비활성화'}")

    # 디렉토리 생성
    Path(settings.CACHE_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.CONVERTED_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    
    # Redis 연결 설정
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    
    # 템플릿 설정
    from fastapi.templating import Jinja2Templates
    BASE_DIR = Path(__file__).parent
    TEMPLATE_DIR = BASE_DIR / "templates"
    templates = Jinja2Templates(directory=TEMPLATE_DIR)
    
    # App state에 저장
    app.state.redis = redis_client
    app.state.templates = templates
    
    logger.info(f"✅ 로그 디렉토리: {settings.LOG_DIR}, 레벨 : {settings.LOG_LEVEL}")
    logger.info(f"✅ 캐시 디렉토리: {settings.CACHE_DIR}")
    logger.info(f"✅ HTML Template 디렉토리: {TEMPLATE_DIR}")
    logger.info(f"✅ 변환된 파일 디렉토리: {settings.CONVERTED_DIR}")
    logger.info(f"✔️ LibreOffice 상태: {'✅ OK' if check_libreoffice()[0] else '❌ ERROR'}")
    
    if redis_client:
        try:
            redis_client.ping()
            logger.info(f"✔️ Redis HOST: {settings.REDIS_HOST} - {settings.REDIS_PORT}")
            logger.info("✅ Redis 연결:  OK")
        except Exception as e:
            logger.error(f"❌ Redis 연결 실패: {e}")
    else:
        logger.warning("❌ Redis:  비활성화")

def shutdown_event():
    """애플리케이션 종료 시 정리 작업"""
    logger.info(f"✅ {settings.APP_NAME} 종료")
    try:
        cleanup_old_cache_files(24)
        logger.info("✅ 캐시 정리 완료")
        logger.info("------------------------------------------------")
        logger.info(f"✳️ 종료: {settings.APP_NAME} v{settings.VERSION}")
        logger.info("------------------------------------------------")

    except Exception as e:
        logger.error(f"❌ 캐시 정리 실패: {e}")

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8003,
        reload=True
    )