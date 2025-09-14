"""
Convert Library
PDF 변환 관련 기능들을 모아놓은 라이브러리
"""
import time
import subprocess
from pathlib import Path

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logger import get_logger
from app.core.utils import copy_and_cache_file, download_and_cache_file

logger = get_logger(__name__)

# aiofiles 사용 가능 여부
try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False


async def convert_to_pdf(request: Request, input_path: Path) -> Path:
    """
    LibreOffice를 사용해 파일을 PDF로 변환 (비동기)
    Returns: 변환된 PDF 파일 경로
    """
    from app.core.utils import libreoffice_convert  # 순환 import 방지
    
    CONVERTED_DIR = Path(settings.CONVERTED_DIR)
    logger.info(f"PDF 변환 시작: {input_path}, 생성폴더: {CONVERTED_DIR}")

    # 이미 PDF인 경우 그대로 반환
    if input_path.suffix.lower() == '.pdf':
        logger.info(f"이미 PDF 파일입니다: {input_path}")
        return input_path
    
    # 변환된 파일 경로
    pdf_filename = f"{input_path.stem}.pdf"
    pdf_path = CONVERTED_DIR / pdf_filename
    
    # 이미 변환된 파일이 있으면 반환
    if pdf_path.exists():
        logger.info(f"이미 변환된 PDF 파일이 존재합니다: {pdf_path}")
        return pdf_path
    
    logger.info(f"출력 디렉토리: {CONVERTED_DIR}")
    stats_manager = request.app.state.stats_db
    try:
        # 범용 LibreOffice 변환 함수 사용
        result_path = await libreoffice_convert(
            input_path=input_path,
            output_dir=CONVERTED_DIR,
            output_format="pdf",
            timeout=60
        )
        
        logger.info(f"PDF 변환 성공: {input_path} -> {result_path}")
        return result_path
        
    except FileNotFoundError as e:
        error_msg = f"입력 파일이 존재하지 않습니다: {input_path}"
        logger.error(error_msg)
        stats_manager.log_error('file', str(input_path), error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except subprocess.TimeoutExpired:
        error_msg = "LibreOffice 변환 시간 초과"
        logger.error(error_msg)
        stats_manager.log_error('file', str(input_path), error_msg)
        raise HTTPException(
            status_code=500,
            detail="문서 변환 시간이 초과되었습니다"
        )
    except RuntimeError as e:
        error_msg = str(e)
        logger.error(f"LibreOffice 변환 실패: {error_msg}")
        stats_manager.log_error('file', str(input_path), error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except Exception as e:
        logger.error(f"PDF 변환 중 예상치 못한 오류: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        stats_manager.log_error('file', str(input_path), error_msg)
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류 발생: {str(e)}"
        )

async def convert_to_html_with_libreoffice(request: Request, input_path: Path) -> Path:
    """
    LibreOffice를 사용해 파일을 HTML로 변환 (비동기)
    특정 파일 타입은 전용 변환 함수 사용 (한글 인코딩 문제 해결)
    Returns: 변환된 HTML 파일 경로
    """
    from app.core.utils import libreoffice_convert  # 순환 import 방지
    
    stats_manager = request.app.state.stats_db
    
    CONVERTED_DIR = Path(settings.CONVERTED_DIR)
    
    # 이미 HTML인 경우 그대로 반환
    if input_path.suffix.lower() in {'.html', '.htm'}:
        return input_path
    
    # 변환된 파일 경로
    html_filename = f"{input_path.stem}.html"
    html_path = CONVERTED_DIR / html_filename
    
    # 이미 변환된 파일이 있으면 반환
    if html_path.exists():
        return html_path
    
    try:
        # 범용 LibreOffice 변환 함수 사용
        result_path = await libreoffice_convert(
            input_path=input_path,
            output_dir=CONVERTED_DIR,
            output_format="html",
            timeout=60
        )
        
        # 출력 파일 경로 검증 및 반환
        if result_path != html_path and html_path.exists():
            # 예상한 경로에 파일이 있으면 그것을 사용
            return html_path
        elif result_path.exists():
            # 변환 함수가 반환한 경로의 파일을 사용
            return result_path
        else:
            # 둘 다 없으면 예외 발생
            raise HTTPException(
                status_code=500,
                detail="변환된 HTML 파일을 찾을 수 없습니다"
            )
            
    except FileNotFoundError as e:
        error_message =  f"입력 파일이 존재하지 않습니다: {input_path}"
        stats_manager.log_error('file', str(input_path), error_message)
        raise HTTPException(
            status_code=500,
            detail=error_message
        )
    except subprocess.TimeoutExpired:
        error_message = "LibreOffice 변환 시간 초과"
        stats_manager.log_error('file', str(input_path), error_message)
        raise HTTPException(
            status_code=500,
            detail=error_message
        )
    except RuntimeError as e:
        error_message = str(e)
        stats_manager.log_error('file', str(input_path), error_message)
        logger.error(f"LibreOffice 변환 실패: {error_message}")
        raise HTTPException(
            status_code=500,
            detail=error_message
        )
    except Exception as e:
        error_message = f"LibreOffice 변환 중 예상치 못한 오류: {type(e).__name__}: {str(e)}"
        stats_manager.log_error('file', str(input_path), error_message)
        logger.error(error_message)
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류 발생: {error_message}"
        )

async def local_file_copy_and_convert(request: Request, path: str, output_format: str) -> str:
    """
    로컬 파일을 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
   
    # redis_client = request.app.state.redis
    stats_manager = request.app.state.stats_db
    start_time = time.time()

    # converted_dir = Path(settings.CONVERTED_DIR)
    if output_format.lower().endswith('pdf'):
        file_path, original_filename, cache_hit = await copy_and_cache_file(request, path,  settings)
        output_path = await convert_to_pdf(request, file_path)

    elif output_format.lower().endswith('html'):
        file_path, original_filename, cache_hit = await copy_and_cache_file(request, path, settings)
        output_path = await convert_to_html_with_libreoffice(request, file_path)

    logger.info(f"path :{path} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/{output_format.lower()}/{output_path.name}"
    logger.info(f"변환된 파일 URL: {url}")
    # 통계 DB에 기록
    end_time = time.time()
    conversion_time = end_time - start_time
    stats_manager.log_conversion(
        source_type="path",
        source_value=path,
        file_name=output_path.name,
        file_type=output_path.suffix[1:],
        file_size=output_path.stat().st_size,
        output_format=output_format,
        conversion_time=conversion_time,
        cache_hit=cache_hit
    )   
    return url

async def url_download_and_convert(request: Request, url: str, output_format: str) -> str:
    """
    URL에서 파일을 다운로드하고 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    stats_manager = request.app.state.stats_db
    start_time = time.time()

    if output_format.lower().endswith('pdf'):
        file_path, original_filename, cache_hit = await download_and_cache_file(request, url, settings)
        output_path = await convert_to_pdf(request, file_path)

    elif output_format.lower().endswith('html'):
        file_path, original_filename, cache_hit = await download_and_cache_file(request, url, settings)
        output_path = await convert_to_html_with_libreoffice(request, file_path)
    
    logger.info(f"url :{url} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/{output_format.lower()}/{output_path.name}"
    logger.info(f"변환된 파일 URL: {url}")
    end_time = time.time()
    conversion_time = end_time - start_time 
    # 통계 DB에 기록
    stats_manager.log_conversion(
        source_type="url",
        source_value=url,
        file_name=output_path.name,
        file_type=output_path.suffix[1:],
        file_size=output_path.stat().st_size,
        output_format=output_format,
        conversion_time=conversion_time,
        cache_hit=cache_hit
    )
    return url

