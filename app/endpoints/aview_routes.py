# aview_routes.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.core.utils import (
    check_libreoffice,
    get_redis,
    get_templates
)
from app.core.config import settings

router = APIRouter()

@router.get("/run-test", response_class=HTMLResponse)
async def run_test(request: Request):
    """테스트용 엔드포인트"""
    templates = get_templates(request)
    context = {
        "request": request,
        "title": "A-View 테스트",
    }
    return templates.TemplateResponse("run_test.html", context)

@router.get("/log-view", response_class=HTMLResponse)
async def log_view(request: Request):
    """로그 뷰어용 엔드포인트"""
    templates = get_templates(request)
    context = {
        "request": request,
        "title": "로그 뷰어",
    }
    return templates.TemplateResponse("log_view.html", context) 

@router.get("/pdf/{filename}")
async def serve_pdf(filename: str):
    """변환된 PDF 파일 다운로드"""
    pdf_path = Path(settings.CONVERTED_DIR) / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )

@router.get("/html/{filename}")
async def serve_html(filename: str):
    """변환된 HTML 파일 다운로드"""
    html_path = Path(settings.CONVERTED_DIR) / filename
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="HTML 파일을 찾을 수 없습니다")

    return FileResponse(
        path=html_path,
        media_type="text/html",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/health")
async def health_check(request: Request):
    """시스템 상태 확인"""
    redis_client = get_redis(request)
    try:
        redis_ping = bool(redis_client.ping()) if redis_client else False
    except Exception:
        redis_ping = False

    libre_ok, _ = check_libreoffice()
    is_healthy = libre_ok and redis_ping

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "services": {
            "libreoffice": libre_ok,
            "redis": redis_ping,
        },
        "version": settings.VERSION,
        "cache_dir": settings.CACHE_DIR,
    }