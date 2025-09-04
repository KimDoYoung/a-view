# aview_routes.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse

from utils import (
    check_libreoffice,
    get_cached_pdf,
    get_redis,
    get_templates
)
from config import settings

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def view_document(
    request: Request,
    url: str = Query(..., description="변환할 문서의 URL"),
    mode: str = Query("embed", description="표시 모드: embed(임베드), download(다운로드)"),
):
    """
    메인 문서 뷰어 엔드포인트
    """
    redis_client = get_redis(request)
    try:
        # URL에서 파일 다운로드 및 PDF 변환 (캐시 포함)
        pdf_path, original_filename = await get_cached_pdf(redis_client, url, settings)

        if mode == "download":
            # 다운로드 모드: PDF 파일 직접 반환
            return FileResponse(
                path=pdf_path,
                filename=f"{Path(original_filename).stem}.pdf",
                media_type="application/pdf",
            )

        # 임베드 모드: PDF 뷰어 HTML 반환
        templates = get_templates(request)
        pdf_url = f"/aview/pdf/{pdf_path.name}"
        context = {
            "request": request,
            "title": f"문서 뷰어 - {original_filename}",
            "pdf_url": pdf_url,
            "original_filename": original_filename,
            "source_url": url,
        }
        return templates.TemplateResponse("viewer.html", context)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"문서 처리 중 오류 발생: {str(e)}")


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