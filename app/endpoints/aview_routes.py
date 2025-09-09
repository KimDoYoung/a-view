# aview_routes.py
"""
모듈 설명: 
    - A-View의 FastAPI 라우터 모듈
    - 주로 system적이면서 내부적인으로 사용하는 엔드포인트들을 정의
주요 기능:
    - get /run-test : 테스트 페이지 제공
    - get /log-view : 로그 뷰어 페이지 제공
    - get /pdf/{filename} : 변환된 PDF 파일 제공
    - get /html/{filename} : 변환된 HTML 파일 제공
    - get /health : 시스템 상태 확인

작성자: 김도영
작성일: 2025-09-08
버전: 1.0
"""
# aview_routes.py
from typing import List
from pathlib import Path
from fastapi import APIRouter, File, Request, HTTPException, UploadFile, UploadFile
from fastapi.params import Query
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
        "title": "API테스트",
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
#-----------------------------------------------------
# run-test / settings.FILES_DIR관련
#-----------------------------------------------------
@router.get("/files")
async def get_files():
    """FILES_DIR 파일 목록 조회"""
    try:
        files_dir = Path(settings.FILES_DIR)
        
        # 디렉토리가 존재하지 않으면 생성
        if not files_dir.exists():
            files_dir.mkdir(parents=True, exist_ok=True)
            return {"success": True, "files": []}
        
        # 파일 목록 가져오기 (파일만, 디렉토리 제외)
        files = []
        for file_path in files_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime
                })
        
        # 수정 시간순으로 정렬 (최신 파일이 먼저)
        files.sort(key=lambda x: x["modified"], reverse=True)
        
        return {"success": True, "files": files}
        
    except Exception as e:
        return {
            "success": False,
            "error_code": "FILES_LIST_ERROR",
            "error_message": f"파일 목록 조회 실패: {str(e)}"
        }

@router.get("/files/{filename}")
async def download_file(filename: str):
    """파일 다운로드"""
    try:
        file_path = Path(settings.FILES_DIR) / filename
        
        if not file_path.exists():
            return {
                "success": False,
                "error_code": "FILE_NOT_FOUND",
                "error_message": f"파일을 찾을 수 없습니다: {filename}"
            }
        
        if not file_path.is_file():
            return {
                "success": False,
                "error_code": "NOT_A_FILE",
                "error_message": f"요청한 항목이 파일이 아닙니다: {filename}"
            }
        
        return FileResponse(
            path=file_path,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
        
    except Exception as e:
        return {
            "success": False,
            "error_code": "FILE_DOWNLOAD_ERROR",
            "error_message": f"파일 다운로드 실패: {str(e)}"
        }

@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """파일 업로드 (멀티파일 지원)"""
    try:
        files_dir = Path(settings.FILES_DIR)
        
        # 디렉토리가 존재하지 않으면 생성
        if not files_dir.exists():
            files_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        
        for file in files:
            if not file.filename:
                continue
                
            file_path = files_dir / file.filename
            
            # 파일 저장 (덮어쓰기)
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            uploaded_files.append({
                "name": file.filename,
                "size": len(content)
            })
        
        return {
            "success": True,
            "message": f"{len(uploaded_files)}개 파일이 업로드되었습니다",
            "uploaded_files": uploaded_files
        }
        
    except Exception as e:
        return {
            "success": False,
            "error_code": "FILE_UPLOAD_ERROR",
            "error_message": f"파일 업로드 실패: {str(e)}"
        }

@router.post("/delete")
async def delete_file(filename: str = Query(..., description="삭제할 파일명")):
    """파일 삭제"""
    try:
        file_path = Path(settings.FILES_DIR) / filename
        
        if not file_path.exists():
            return {
                "success": False,
                "error_code": "FILE_NOT_FOUND",
                "error_message": f"파일을 찾을 수 없습니다: {filename}"
            }
        
        if not file_path.is_file():
            return {
                "success": False,
                "error_code": "NOT_A_FILE",
                "error_message": f"요청한 항목이 파일이 아닙니다: {filename}"
            }
        
        file_path.unlink()
        
        return {
            "success": True,
            "message": f"파일이 삭제되었습니다: {filename}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error_code": "FILE_DELETE_ERROR",
            "error_message": f"파일 삭제 실패: {str(e)}"
        }

@router.post("/delete-all")
async def delete_all_files():
    """모든 파일 삭제"""
    try:
        files_dir = Path(settings.FILES_DIR)
        
        if not files_dir.exists():
            return {
                "success": True,
                "message": "삭제할 파일이 없습니다",
                "deleted_count": 0
            }
        
        deleted_files = []
        
        # 파일만 삭제 (디렉토리는 제외)
        for file_path in files_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()
                deleted_files.append(file_path.name)
        
        return {
            "success": True,
            "message": f"{len(deleted_files)}개 파일이 삭제되었습니다",
            "deleted_count": len(deleted_files),
            "deleted_files": deleted_files
        }
        
    except Exception as e:
        return {
            "success": False,
            "error_code": "FILES_DELETE_ALL_ERROR",
            "error_message": f"전체 파일 삭제 실패: {str(e)}"
        }