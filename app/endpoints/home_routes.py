# home_routes.py
"""
모듈 설명: 
    - 외부 API 및 메인 페이지 엔드포인트 모음
주요 기능:
    - get / : 메인 페이지 제공
    - post /convert : 문서 변환 API 제공
    - get /view : 문서 뷰어 API 제공
    - get /download : 변환된 파일 다운로드 API 제공
    - get /download-original : 원본 파일 다운로드 API 제공
    - get /image : 이미지 파일 서빙 API 제공
    - get /about : 소개 페이지 제공


작성자: 김도영
작성일: 2025-09-08
버전: 1.0
"""
import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from app.core.config import settings
from app.core.convert_lib import local_file_copy_and_convert, url_download_and_convert
from app.core.logger import get_logger
from app.core.utils import (
    check_libreoffice,
    extract_hash_from_url,
    get_redis,
    get_templates,
)
from app.core.view_lib import local_file_copy_and_view, url_download_and_view
from app.domain.schemas import (
    ConvertParams,
    ConvertRequest,
    ConvertResponse,
    OutputFormat,
    ViewParams,
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지 - 서비스 상태 및 테스트 UI"""
    templates = get_templates(request)
    libre_status = check_libreoffice()

    # Redis 연결 상태 확인
    redis_client = get_redis(request)
    try:
        redis_status = bool(redis_client.ping()) if redis_client else False
    except Exception:
        redis_status = False

    context = {
        "request": request,
        "title": "A-View - Document Viewer for AssetERP",
        "libre_status": libre_status,
        "redis_status": redis_status,
        "version": settings.VERSION,
    }
    return templates.TemplateResponse("index.html", context)

@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    """소개 페이지"""
    templates = get_templates(request)
    context = {
        "request": request,
        "title": "소개",
        "version": settings.VERSION,
    }
    return templates.TemplateResponse("about.html", context)

#-----------------------------------------------------
# 문서 변환 API : convert (GET/POST)
#-----------------------------------------------------
@router.get("/convert", response_model=ConvertResponse)
async def convert_document(
    request: Request,
    url: Optional[str] = Query(None, description="변환할 문서의 URL"),
    path: Optional[str] = Query(None, description="변환할 문서의 로컬 경로"),
    output: OutputFormat = Query(OutputFormat.HTML, description="출력 형식 (pdf 또는 html)")
) -> ConvertResponse:
    """
    문서 변환 API
    
    사용법:
    - URL: /convert?url=https://example.com/file.pdf&output=html
    - 경로: /convert?path=c:\\myfolder\\1.docx&output=pdf
    """
    try:
        # ConvertParams 생성 시 validation 오류 처리
        params = ConvertParams(url=url, path=path, output=output)
        
        if params.is_url_source:
            logger.info(f"URL에서 다운로드: {params.url}")
            converted_url = await url_download_and_convert(request, params.url, params.output)
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"URL 문서가 {params.output} 형식으로 변환되었습니다"
            )
        else:
            logger.info(f"로컬 파일 변환: {params.path}")
            converted_url = await local_file_copy_and_convert(request, params.path, params.output)
            
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"로컬 파일이 {params.output} 형식으로 변환되었습니다"
            )
            
    except ValueError as e:
        # 검증 오류 (파일 존재하지 않음, URL 형식 오류 등)
        logger.error(f"Validation error: {str(e)}")
        return ConvertResponse.error_response(f"입력 오류: {str(e)}")
    except FileNotFoundError as e:
        # 파일 없음 오류
        logger.error(f"File not found: {str(e)}")
        return ConvertResponse.error_response(f"파일을 찾을 수 없습니다: {str(e)}")
    except Exception as e:
        # 기타 오류
        logger.error(f"Unexpected error: {str(e)}")
        return ConvertResponse.error_response(f"변환 중 오류가 발생했습니다: {str(e)}")
    
@router.post("/convert", response_model=ConvertResponse)
async def convert_document_post(request: Request, convert_request: ConvertRequest) -> ConvertResponse:
    """POST 방식 변환"""
    # redis_client = get_redis(request)
    try:
        params = ConvertParams(**convert_request.model_dump())
        
        if params.is_url_source:
            logger.info(f"POST URL에서 다운로드: {params.url}")
            converted_url = await url_download_and_convert(request, params.url, params.output)
            
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"URL 문서가 {params.output} 형식으로 변환되었습니다"
            )
        else:
            logger.info(f"POST 로컬 파일 변환: {params.path}")
            converted_url = await local_file_copy_and_convert(request, params.path, params.output)
            
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"로컬 파일이 {params.output} 형식으로 변환되었습니다"
            )
            
    except ValueError as e:
        logger.error(f"POST validation error: {str(e)}")
        return ConvertResponse.error_response(f"입력 오류: {str(e)}")
    except FileNotFoundError as e:
        logger.error(f"POST file not found: {str(e)}")
        return ConvertResponse.error_response(f"파일을 찾을 수 없습니다: {str(e)}")
    except Exception as e:
        logger.error(f"POST unexpected error: {str(e)}")
        return ConvertResponse.error_response(f"변환 중 오류가 발생했습니다: {str(e)}")
    
#-----------------------------------------------------
# 문서 뷰어 API : view (GET)
#-----------------------------------------------------
@router.get("/view", response_class=HTMLResponse)
async def view_document(
    request: Request,
    url: Optional[str] = Query(None, description="보기할 문서의 URL"),
    path: Optional[str] = Query(None, description="보기할 문서의 로컬 경로")
) -> HTMLResponse:
    """
    문서 뷰어 API - 파일 확장자에 따라 자동으로 출력 포맷 결정
    
    사용법:
    - URL: /view?url=https://example.com/file.docx (자동으로 PDF 변환)
    - 경로: /view?path=c:\\myfolder\\1.txt (자동으로 HTML 변환)
    """
    try:
        # ViewParams 생성 시 validation 오류 처리
        params = ViewParams(url=url, path=path)
        
        # 자동으로 결정된 출력 포맷 사용
        auto_output = params.auto_output_format
        
        if params.is_url_source:
            logger.info(f"URL에서 다운로드 및 보기: {params.url} -> {auto_output.value}")
            converted_url = await url_download_and_view(request, params.url, auto_output)
            hashcode = extract_hash_from_url(converted_url)
            converted_original_url = f"/aview/{auto_output.value}/{hashcode}.{auto_output.value}"
            # URL에서 원본 파일명 추출 및 디코딩
            
            parsed_url = urlparse(params.url)
            original_filename = unquote(Path(parsed_url.path).name, encoding='utf-8')
            
            templates = get_templates(request)
            context = {
                "request": request,
                "title": f"문서 뷰어-{original_filename}",
                "converted_url": converted_url,
                "original_source": params.url,
                "original_filename": original_filename,
                "original_url": params.url,  # 원본 다운로드용
                "source_origin": "url",
                "output_format": auto_output.value,
                "converted_original_url": converted_original_url,
            }
            template_name = f"view_{auto_output.value}.html"
            return templates.TemplateResponse(template_name, context)
        else:
            logger.info(f"path 파일 변환: {params.path} -> {auto_output.value}")
            converted_url = await local_file_copy_and_view(request, params.path, auto_output)
            
            # 로컬 파일에서 원본 파일명 추출
            original_filename = Path(params.path).name
            original_filename = unquote(original_filename, encoding='utf-8')
            
            templates = get_templates(request)
            context = {
                "request": request,
                "title": f"문서 뷰어-{original_filename}",
                "converted_url": converted_url,
                "original_source": params.path,
                "original_filename": original_filename,
                "original_path": params.path,  # 원본 다운로드용
                "source_origin": "path",
                "output_format": auto_output.value
            }
            template_name = f"view_{auto_output.value}.html"
            return templates.TemplateResponse(template_name, context)
            
    except ValueError as e:
        # 검증 오류 (파일 존재하지 않음, URL 형식 오류 등)
        logger.error(f"Validation error: {str(e)}")
        templates = get_templates(request)
        context = {
            "request": request,
            "title": "문서 뷰어 - 입력 오류",
            "error_type": "validation",
            "error_title": "입력 오류",
            "error_message": str(e),
            "original_source": url or path or "알 수 없음",
            "source_origin": "url" if url else "path",
            "output_format": "html"
        }
        return templates.TemplateResponse("view_error.html", context)
    except FileNotFoundError as e:
        # 파일 없음 오류
        logger.error(f"File not found: {str(e)}")
        templates = get_templates(request)
        context = {
            "request": request,
            "title": "문서 뷰어 - 파일 없음",
            "error_type": "file_not_found",
            "error_title": "파일을 찾을 수 없습니다",
            "error_message": str(e),
            "original_source": url or path or "알 수 없음",
            "source_origin": "url" if url else "path",
            "output_format": "html"
        }
        return templates.TemplateResponse("view_error.html", context)
    except Exception as e:
        # 기타 오류
        logger.error(f"Unexpected error: {str(e)}")
        templates = get_templates(request)
        context = {
            "request": request,
            "title": "문서 뷰어 - 서버 오류",
            "error_type": "server_error",
            "error_title": "서버 오류가 발생했습니다",
            "error_message": str(e),
            "original_source": url or path or "알 수 없음",
            "source_origin": "url" if url else "path",
            "output_format": "html"
        }
        return templates.TemplateResponse("view_error.html", context)


#-----------------------------------------------------
# 파일 다운로드 API : download (GET)
#-----------------------------------------------------
@router.get("/download")
async def download_file(
    request: Request,
    file_path: str = Query(..., description="다운로드할 파일의 서버 경로"),
    filename: Optional[str] = Query(None, description="다운로드 파일명")
):
    """
    변환된 파일 다운로드 API
    
    사용법:
    - /download?file_path=/converted/xxx.pdf&filename=document.pdf
    """
    try:
        # 파일 경로 검증 및 보안 체크
        logger.info(f"다운로드 요청 받은 파일 경로: {file_path}")
        
        # URL 경로에서 실제 파일 경로 추출
        # 예: /aview/html/test.html -> test.html
        if file_path.startswith('/aview/'):
            # /aview/html/filename 또는 /aview/pdf/filename 형태
            path_parts = file_path.split('/')
            if len(path_parts) >= 3:
                actual_filename = path_parts[-1]  # 마지막 부분이 실제 파일명
                logger.info(f"추출된 파일명: {actual_filename}")
                
                from app.core.config import settings
                file_path_obj = Path(settings.CONVERTED_DIR) / actual_filename
            else:
                raise ValueError(f"잘못된 파일 경로 형식: {file_path}")
        else:
            # 일반적인 경로 처리
            file_path_obj = Path(file_path)
            
            # 절대 경로가 아닌 경우 converted 디렉토리 기준으로 처리
            if not file_path_obj.is_absolute():
                from app.core.config import settings
                file_path_obj = Path(settings.CONVERTED_DIR) / file_path
        
        logger.info(f"최종 파일 경로: {file_path_obj}")
        
        if not file_path_obj.exists():
            logger.error(f"다운로드할 파일이 존재하지 않습니다: {file_path_obj}")
            return HTMLResponse(content="<h3>파일을 찾을 수 없습니다</h3>", status_code=404)
        
        if not file_path_obj.is_file():
            logger.error(f"다운로드할 경로가 파일이 아닙니다: {file_path_obj}")
            return HTMLResponse(content="<h3>올바른 파일이 아닙니다</h3>", status_code=400)
        
        # 파일명이 제공되지 않은 경우 원본 파일명 사용
        download_filename = filename or file_path_obj.name
        
        logger.info(f"파일 다운로드: {file_path_obj} as {download_filename}")

        return FileResponse(
            path=file_path_obj,
            filename=download_filename,
            media_type='application/octet-stream'
        )
        
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return HTMLResponse(content=f"<h3>다운로드 중 오류가 발생했습니다: {str(e)}</h3>", status_code=500)


#-----------------------------------------------------
# 원본 파일 다운로드 API : download-original (GET)
#-----------------------------------------------------
@router.get("/download-original")
async def download_original_file(
    request: Request,
    url: Optional[str] = Query(None, description="원본 URL (URL 소스인 경우)"),
    path: Optional[str] = Query(None, description="원본 로컬 경로 (경로 소스인 경우)"),
    filename: Optional[str] = Query(None, description="다운로드 파일명")
):
    """
    원본 파일 다운로드 API
    
    사용법:
    - URL 소스: /download-original?url=http://example.com/file.txt&filename=file.txt
    - 로컬 소스: /download-original?path=c:/temp/file.txt&filename=file.txt
    """
    try:
        if url:
            # URL에서 원본 파일 다운로드
            logger.info(f"원본 URL 다운로드 요청: {url}")            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # 파일명 결정
                if not filename:
                    parsed_url = urlparse(url)
                    filename = unquote(Path(parsed_url.path).name, encoding='utf-8') or "download_file"
                
                logger.info(f"URL에서 원본 파일 다운로드: {filename}")
                
                # 직접 파일 내용을 Response로 반환
                return Response(
                    content=response.content,
                    media_type='application/octet-stream',
                    headers={"Content-Disposition": f"attachment; filename={filename}"}
                )
                
        elif path:
            # 로컬 파일 다운로드
            logger.info(f"원본 로컬 파일 다운로드 요청: {path}")
            
            file_path_obj = Path(path)
            
            if not file_path_obj.exists():
                logger.error(f"원본 파일이 존재하지 않습니다: {file_path_obj}")
                return HTMLResponse(content="<h3>원본 파일을 찾을 수 없습니다</h3>", status_code=404)
            
            if not file_path_obj.is_file():
                logger.error(f"원본 경로가 파일이 아닙니다: {file_path_obj}")
                return HTMLResponse(content="<h3>올바른 파일이 아닙니다</h3>", status_code=400)
            
            # 파일명 결정
            download_filename = filename or file_path_obj.name
            
            logger.info(f"로컬에서 원본 파일 다운로드: {file_path_obj} as {download_filename}")
            
            return FileResponse(
                path=file_path_obj,
                filename=download_filename,
                media_type='application/octet-stream'
            )
            
        else:
            return HTMLResponse(content="<h3>URL 또는 경로가 필요합니다</h3>", status_code=400)
            
    except Exception as e:
        logger.error(f"원본 파일 다운로드 오류: {str(e)}")
        return HTMLResponse(content=f"<h3>원본 파일 다운로드 중 오류가 발생했습니다: {str(e)}</h3>", status_code=500)


#-----------------------------------------------------
# 이미지 서빙 API : image
#-----------------------------------------------------
@router.get("/image")
async def serve_image(request: Request, path: str = Query(..., description="이미지 파일 경로")):
    """
    이미지 파일 서빙 API
    이미지 뷰어에서 실제 이미지를 표시하기 위한 엔드포인트
    """
    try:        
        # 경로 정규화
        image_path = Path(path)
        
        # 보안: 경로 순회 공격 방지
        if not image_path.is_absolute():
            logger.error(f"절대 경로가 아닙니다: {path}")
            return HTMLResponse(content="<h3>잘못된 경로입니다</h3>", status_code=400)
        
        # 파일 존재 확인
        if not image_path.exists():
            logger.error(f"이미지 파일이 존재하지 않습니다: {image_path}")
            return HTMLResponse(content="<h3>이미지를 찾을 수 없습니다</h3>", status_code=404)
        
        if not image_path.is_file():
            logger.error(f"이미지 경로가 파일이 아닙니다: {image_path}")
            return HTMLResponse(content="<h3>올바른 파일이 아닙니다</h3>", status_code=400)
        
        # 이미지 파일 형식 확인
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type or not mime_type.startswith('image/'):
            logger.error(f"이미지 파일이 아닙니다: {image_path}, MIME: {mime_type}")
            return HTMLResponse(content="<h3>이미지 파일이 아닙니다</h3>", status_code=400)
        
        logger.info(f"이미지 서빙(/image): {image_path}, MIME: {mime_type}")
        
        return FileResponse(
            path=image_path,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=3600"}  # 1시간 캐시
        )
        
    except Exception as e:
        logger.error(f"이미지 서빙 오류: {str(e)}")
        return HTMLResponse(content=f"<h3>이미지 서빙 중 오류가 발생했습니다: {str(e)}</h3>", status_code=500)