

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional

from app.domain.schemas import ConvertParams, ConvertRequest, ConvertResponse, OutputFormat
from app.utils import check_libreoffice, local_file_copy_and_convert, url_download_and_convert
from app.utils import get_redis, get_templates
from logger import get_logger

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
        "title": "A-View Document Processor",
        "libre_status": libre_status,
        "redis_status": redis_status,
    }
    return templates.TemplateResponse("index.html", context)


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
    redis_client = get_redis(request)
    try:
        # ConvertParams 생성 시 validation 오류 처리
        params = ConvertParams(url=url, path=path, output=output)
        
        if params.is_url_source:
            logger.info(f"URL에서 다운로드: {params.url}")
            converted_url = await url_download_and_convert(redis_client,params.url, params.output)
            
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"URL 문서가 {params.output} 형식으로 변환되었습니다"
            )
        else:
            logger.info(f"로컬 파일 변환: {params.path}")
            converted_url = await local_file_copy_and_convert(redis_client, params.path, params.output)
            
            return ConvertResponse.success_response(
                url=converted_url,
                message=f"로칼 파일이 {params.output} 형식으로 변환되었습니다"
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
async def convert_document_post(request: ConvertRequest) -> ConvertResponse:
    """POST 방식 변환"""
    try:
        params = ConvertParams(**request.model_dump())
        return await convert_document(
            url=params.url, 
            path=params.path, 
            output=params.output
        )
    except ValueError as e:
        logger.error(f"POST validation error: {str(e)}")
        return ConvertResponse.error_response(f"입력 오류: {str(e)}")
    except Exception as e:
        logger.error(f"POST unexpected error: {str(e)}")
        return ConvertResponse.error_response(f"변환 중 오류가 발생했습니다: {str(e)}")
    
#-----------------------------------------------------
# 문서 뷰어 API : view (GET)
#-----------------------------------------------------
@router.get("/view", response_class=HTMLResponse)
async def view_document(
    request: Request,
    url: Optional[str] = Query(None, description="변환할 문서의 URL"),
    path: Optional[str] = Query(None, description="변환할 문서의 로컬 경로"),
    output: OutputFormat = Query(OutputFormat.HTML, description="출력 형식 (pdf 또는 html)")
) -> HTMLResponse:
    """
    문서 뷰어 API
    
    사용법:
    - URL: /view?url=https://example.com/file.pdf&output=html
    - 경로: /view?path=c:\\myfolder\\1.docx&output=pdf
    """
    redis_client = get_redis(request)
    try:
        # ConvertParams 생성 시 validation 오류 처리
        params = ConvertParams(url=url, path=path, output=output)
        
        if params.is_url_source:
            logger.info(f"URL에서 다운로드 및 변환: {params.url}")
            converted_url = await url_download_and_convert(redis_client,params.url, params.output)
            
            templates = get_templates(request)
            context = {
                "request": request,
                "title": "문서 뷰어",
                "converted_url": converted_url,
                "original_source": params.url,
                "source_origin": "url",
                "output_format": params.output.value
            }
            template_name = f"view_{params.output.value}.html"
            return templates.TemplateResponse(template_name, context)
        else:
            logger.info(f"로컬 파일 변환: {params.path}")
            converted_url = await local_file_copy_and_convert(redis_client, params.path, params.output)
            
            templates = get_templates(request)
            context = {
                "request": request,
                "title": "문서 뷰어",
                "converted_url": converted_url,
                "original_source": params.path,
                "source_origin": "path",
                "output_format": params.output.value
            }
            template_name = f"view_{params.output.value}.html"
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
            "output_format": output.value if output else "html"
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
            "output_format": output.value if output else "html"
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
            "output_format": output.value if output else "html"
        }
        return templates.TemplateResponse("view_error.html", context)