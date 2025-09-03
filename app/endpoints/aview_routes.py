# aview_routes.py
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse

from utils import (
    check_libreoffice,
    get_cached_pdf,
    CONVERTED_DIR,
)

router = APIRouter()


def _get_redis(request: Request):
    # main.py에서 app.state.redis에 넣어둔 인스턴스를 꺼내씀
    return getattr(request.app.state, "redis", None)


def _get_templates(request: Request):
    # main.py에서 app.state.templates에 넣어둔 인스턴스를 꺼내씀
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지 - 서비스 상태 및 테스트 UI"""
    templates = _get_templates(request)
    libre_status = check_libreoffice()

    # Redis 연결 상태 확인
    redis_client = _get_redis(request)
    try:
        redis_status = bool(redis_client.ping()) if redis_client else False
    except Exception:
        redis_status = False

    context = {
        "request": request,
        "title": "A-View Document Processor",
        "libre_status": libre_status,
        "redis_status": redis_status,
    }
    return templates.TemplateResponse("index.html", context)


@router.get("/aview", response_class=HTMLResponse)
async def view_document(
    request: Request,
    url: str = Query(..., description="변환할 문서의 URL"),
    mode: str = Query("embed", description="표시 모드: embed(임베드), download(다운로드)"),
):
    """
    메인 문서 뷰어 엔드포인트
    """
    redis_client = _get_redis(request)
    try:
        # URL에서 파일 다운로드 및 PDF 변환 (캐시 포함)
        pdf_path, original_filename = await get_cached_pdf(url, redis_client)

        if mode == "download":
            # 다운로드 모드: PDF 파일 직접 반환
            return FileResponse(
                path=pdf_path,
                filename=f"{Path(original_filename).stem}.pdf",
                media_type="application/pdf",
            )

        # 임베드 모드: PDF 뷰어 HTML 반환
        templates = _get_templates(request)
        pdf_url = f"/pdf/{pdf_path.name}"
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
    """변환된 PDF 파일 서빙"""
    pdf_path = CONVERTED_DIR / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/api/health")
async def health_check(request: Request):
    """시스템 상태 확인"""
    redis_client = _get_redis(request)
    try:
        redis_ping = bool(redis_client.ping()) if redis_client else False
    except Exception:
        redis_ping = False

    return {
        "status": "healthy",
        "services": {
            "libreoffice": check_libreoffice(),
            "redis": redis_ping,
        },
        "version": "1.0.0",
        "cache_dir": "/tmp/aview_cache",
    }
