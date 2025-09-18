"""
A-View: LibreOffice 기반 문서 뷰어 서비스
AssetERP의 문서 뷰어로 사용되며, 외부 URL의 Office 문서를 PDF로 변환하여 표시
"""

import signal
import sys
from pathlib import Path

from app.core.sys_info import get_environment_summary

# 프로젝트 루트 디렉토리를 sys.path에 추가 (python ./app/main.py 실행을 위해)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import redis
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logger import get_logger
from app.core.stat_scheduler import StatsScheduler
from app.core.stats_db import StatsDatabase
from app.core.utils import check_libreoffice, cleanup_old_cache_files
from app.endpoints.aview_routes import router as aview_router
from app.endpoints.cache_routes import router as cache_router
from app.endpoints.home_routes import router as home_router
from app.endpoints.stats_routes import router as stats_router

logger = get_logger(__name__)

def signal_handler(signum, frame):
    """Signal handler for graceful shutdown"""
    print(f"🔄 신호 {signum} 받음 - 종료 시작...")
    sys.stderr.write(f"🔄 신호 {signum} 받음 - 종료 시작...\n")
    sys.stderr.flush()
    
    # 여기서 정리 작업 수행
    if hasattr(signal_handler, 'app') and signal_handler.app:
        try:
            if hasattr(signal_handler.app.state, 'scheduler') and signal_handler.app.state.scheduler:
                signal_handler.app.state.scheduler.stop_scheduler()
                print("✅ 스케줄러 종료 완료")
        except Exception as e:
            print(f"❌ 종료 중 오류: {e}")
    
    print("✅ 종료 완료")
    
    # 더 부드러운 종료를 위해 asyncio 루프 정리
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop()
    except:
        pass
    
    # 프로세스 종료
    import os
    os._exit(0)  # sys.exit(0) 대신 더 강력한 종료

# 신호 등록
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 종료 신호

def create_app() -> FastAPI:
    app = FastAPI(
        title="A-View",
        description="Document viewer for AssetERP",
        version=settings.VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
    )
    add_routes(app)
    add_statics(app)
    add_events(app)
    
    # signal handler에 app 전달
    signal_handler.app = app
    
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
    app.include_router(stats_router, prefix="/stats", tags=["statistics"])

def add_events(app: FastAPI):
    app.add_event_handler("startup", lambda: startup_event(app))
    app.add_event_handler("shutdown", lambda: shutdown_event(app))

def startup_event(app: FastAPI):
    """애플리케이션 시작 시 초기화 작업"""
    print("🚀 startup_event 시작!")  # 시작 확인용
    logger.info("------------------------------------------------")
    logger.info(f"✳️ 시작: {settings.APP_NAME} v{settings.VERSION} profile: {settings.PROFILE_NAME}")
    logger.info("------------------------------------------------")
    env_summary = get_environment_summary()
    logger.info(f"🔴 실행 위치 : {env_summary}")
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
    
    # 통계 DB
    stats_manager = StatsDatabase(settings.STATS_DB_PATH)

    # 템플릿 설정
    from fastapi.templating import Jinja2Templates
    BASE_DIR = Path(__file__).parent
    TEMPLATE_DIR = BASE_DIR / "templates"
    templates = Jinja2Templates(directory=TEMPLATE_DIR)
    
    # App state에 저장
    app.state.redis = redis_client
    app.state.templates = templates
    app.state.stats_db = stats_manager
    
    # 스케줄러 생성 및 시작
    scheduler = StatsScheduler(stats_manager)
    scheduler.start_scheduler()
    app.state.scheduler = scheduler  # app.state에 저장
    
    
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
    logger.info(f"✅ 통계 DB 경로: {settings.STATS_DB_PATH}")
    logger.info("✅ 통계 스케줄러 시작됨")
    logger.info(f"✔️ 통계 daily 시각: {settings.EVERY_DAY_AT}, 매주 일요일 정리 시각: {settings.EVERY_SUNDAY_AT}")
    logger.info(f"✅ {settings.APP_NAME} v{settings.VERSION} 초기화 완료")

def shutdown_event(app: FastAPI):
    """애플리케이션 종료 시 정리 작업"""
    import sys
    sys.stderr.write("🔄 종료 시작...\n")
    sys.stderr.flush()
    print(f"🔄 {settings.APP_NAME} 종료 시작...")  # 이 한 줄이 핵심!
    logger.info(f"✅ {settings.APP_NAME} 종료")
    try:
        # 스케줄러 종료
        if hasattr(app.state, 'scheduler') and app.state.scheduler:
            app.state.scheduler.stop_scheduler()
            logger.info("✅ 통계 스케줄러 종료 완료")
        
        # 캐시 정리
        cleanup_old_cache_files(24)
        logger.info("✅ 캐시 정리 완료")
        
        logger.info("------------------------------------------------")
        logger.info(f"✳️ 종료: {settings.APP_NAME} v{settings.VERSION}")
        logger.info("------------------------------------------------")

    except Exception as e:
        logger.error(f"❌ 종료 처리 실패: {e}")

app = create_app()

def run_server():
    is_https = (settings.PROTOCOL.lower() == "https")

    uvicorn_kwargs = dict(
        app="app.main:app",  # 혹은 app 객체 자체
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower(),  # 필요시
    )

    if is_https:
        cert = settings.SSL_CERT_FILE
        key = settings.SSL_KEY_FILE
        ca  = settings.SSL_CA_FILE

        # 파일 존재 체크 (운영버그 방지)
        if not cert or not Path(cert).exists():
            raise FileNotFoundError(f"SSL_CERT_FILE not found: {cert}")
        if not key or not Path(key).exists():
            raise FileNotFoundError(f"SSL_KEY_FILE not found: {key}")

        uvicorn_kwargs.update(
            ssl_certfile=cert,
            ssl_keyfile=key,
        )
        if settings.SSL_KEY_PASSWORD:
            uvicorn_kwargs.update(ssl_keyfile_password=settings.SSL_KEY_PASSWORD)
        if ca and Path(ca).exists():
            uvicorn_kwargs.update(ssl_ca_certs=ca)

    uvicorn.run(**uvicorn_kwargs)

if __name__ == "__main__":
    run_server()
