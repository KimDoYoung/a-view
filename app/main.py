"""
A-View: LibreOffice 기반 문서 뷰어 서비스
AssetERP의 문서 뷰어로 사용되며, 외부 URL의 Office 문서를 PDF로 변환하여 표시
"""

import os
from pathlib import Path

import redis
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from utils import (
    check_libreoffice,
    init_cache_directories,
    get_cached_pdf,
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

# 캐시 디렉토리 초기화
init_cache_directories()

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
    app_logger.info(f"🚀 {settings.app_name} v{settings.app_version} 시작")
    app_logger.info(f"📁 캐시 디렉토리: {settings.cache_dir}")
    app_logger.info(f"🔧 LibreOffice 상태: {'✅ OK' if check_libreoffice() else '❌ ERROR'}")
    
    if redis_client:
        try:
            redis_client.ping()
            app_logger.info("📦 Redis 연결: ✅ OK")
        except Exception as e:
            app_logger.error(f"📦 Redis 연결 실패: {e}")
    else:
        app_logger.warning("📦 Redis: ❌ 비활성화")

@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리 작업"""
    app_logger.info(f"🛑 {settings.app_name} 종료")
    try:
        cleanup_old_cache_files(24)
        app_logger.info("캐시 정리 완료")
    except Exception as e:
        app_logger.error(f"캐시 정리 실패: {e}")

# 홈 페이지
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지 - 서비스 상태 및 테스트 UI"""
    # LibreOffice 상태 확인
    libre_status = check_libreoffice()
    
    # Redis 연결 상태 확인
    try:
        redis_client.ping()
        redis_status = True
    except Exception:
        redis_status = False
    
    context = {
        "request": request,
        "title": "A-View Document Processor",
        "libre_status": libre_status,
        "redis_status": redis_status
    }
    
    return templates.TemplateResponse("index.html", context)

# 메인 문서 뷰어 엔드포인트
@app.get("/aview", response_class=HTMLResponse)
async def view_document(
    request: Request,
    url: str = Query(..., description="변환할 문서의 URL"),
    mode: str = Query("embed", description="표시 모드: embed(임베드), download(다운로드)")
):
    """
    AssetERP에서 호출하는 메인 문서 뷰어
    iframe 소스: http://a-view-host:8003/aview?url=https://asset-erp-host/.../document.xlsx
    """
    try:
        # URL에서 파일 다운로드 및 PDF 변환
        pdf_path, original_filename = await get_cached_pdf(url, redis_client)
        
        if mode == "download":
            # 다운로드 모드: PDF 파일 직접 반환
            return FileResponse(
                path=pdf_path,
                filename=f"{Path(original_filename).stem}.pdf",
                media_type="application/pdf"
            )
        else:
            # 임베드 모드: PDF 뷰어 HTML 반환
            pdf_url = f"/pdf/{pdf_path.name}"
            context = {
                "request": request,
                "title": f"문서 뷰어 - {original_filename}",
                "pdf_url": pdf_url,
                "original_filename": original_filename,
                "source_url": url
            }
            return templates.TemplateResponse("viewer.html", context)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 처리 중 오류 발생: {str(e)}"
        )

# PDF 파일 서빙
@app.get("/pdf/{filename}")
async def serve_pdf(filename: str):
    """변환된 PDF 파일 서빙"""
    from utils import CONVERTED_DIR
    
    pdf_path = CONVERTED_DIR / filename
    
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다")
    
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"}
    )

# 상태 체크 API
@app.get("/api/health")
async def health_check():
    """시스템 상태 확인"""
    try:
        redis_ping = redis_client.ping()
    except Exception:
        redis_ping = False
    
    return {
        "status": "healthy",
        "services": {
            "libreoffice": check_libreoffice(),
            "redis": redis_ping
        },
        "version": "1.0.0",
        "cache_dir": "/tmp/aview_cache"
    }

# 캐시 관리 API
@app.post("/api/cache/cleanup")
async def cleanup_cache(max_age_hours: int = Query(24, description="삭제할 파일의 최대 나이(시간)")):
    """캐시 파일 정리"""
    try:
        cleanup_old_cache_files(max_age_hours)
        return {"status": "success", "message": f"{max_age_hours}시간 이상된 캐시 파일을 정리했습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"캐시 정리 실패: {str(e)}")

@app.get("/api/cache/stats")
async def cache_stats():
    """캐시 통계 정보"""
    from utils import CACHE_DIR, CONVERTED_DIR
    
    try:
        cache_files = list(CACHE_DIR.glob("*"))
        converted_files = list(CONVERTED_DIR.glob("*.pdf"))
        
        cache_size = sum(f.stat().st_size for f in cache_files if f.is_file())
        converted_size = sum(f.stat().st_size for f in converted_files if f.is_file())
        
        return {
            "cache": {
                "files": len([f for f in cache_files if f.is_file()]),
                "size_mb": round(cache_size / (1024 * 1024), 2)
            },
            "converted": {
                "files": len(converted_files),
                "size_mb": round(converted_size / (1024 * 1024), 2)
            },
            "total_size_mb": round((cache_size + converted_size) / (1024 * 1024), 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")

# 레거시 API (기존 테스트용)
@app.post("/api/convert")
async def convert_document_legacy(request: Request):
    """레거시 변환 API (테스트용)"""
    return {
        "status": "info", 
        "message": "새로운 /aview 엔드포인트를 사용하세요"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=True
    )