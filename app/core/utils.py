"""
A-View 유틸리티 함수들
- 간단한 헬퍼 함수들만 포함
- 복잡한 변환 로직은 convert_lib, view_lib 참조
"""
import asyncio
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import aiofiles
import aiohttp
import httpx
from fastapi import HTTPException, Request

# Pygments CSS 스타일 생성
from pygments.formatters import HtmlFormatter

from app.core.config import Config, settings
from app.core.logger import get_logger
from app.domain.file_ext_definition import IMAGE_BASE_EXTENSION, SUPPORTED_EXTENSIONS

logger = get_logger(__name__)

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False

def get_redis(request):
    return getattr(request.app.state, "redis", None)

def get_templates(request):
    return request.app.state.templates

def extract_hash_from_url(url: str) -> Optional[str]:
    """
    URL에서 해시 부분(32자리 16진수)을 추출
    예: http://localhost:8003/aview/html/7637053a13073e9c554736621d1c2ea1.html
        -> "7637053a13073e9c554736621d1c2ea1"
    """
    match = re.search(r'/([a-f0-9]{32})\.(html|pdf)$', url)
    if match:
        return match.group(1)
    return None

def is_image_file(filename: str) -> bool:
    """
    파일명으로 이미지 파일인지 확인
    
    Args:
        filename: 확인할 파일명
        
    Returns:
        bool: 이미지 파일이면 True, 아니면 False
    """
    if not filename:
        return False
    
    try:
        # 확장자 추출 및 소문자 변환
        ext = Path(filename).suffix.lower()
        return ext in IMAGE_BASE_EXTENSION
    except Exception:
        return False

def find_soffice() -> Optional[Path]:
    """
    LibreOffice CLI 실행 파일을 찾는다.
    - Windows: soffice.com(우선) → soffice.exe
    - Linux/macOS: libreoffice → soffice
    - 환경변수/기본 설치 경로도 시도
    """
    if os.name == "nt":
        # 일반적인 설치 경로 시도
        candidates = [
            Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
            Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.com"),
            Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
        ]
        for cand in candidates:
            if cand.exists():
                return cand

        return None
    else:
        # Unix 계열
        for name in ("libreoffice", "soffice"):
            p = shutil.which(name)
            if p:
                return Path(p)
        return None

def check_libreoffice() -> Tuple[bool, str]:
    """
    LibreOffice(soffice) 사용 가능 여부를 확인하고 버전 문자열을 반환.
    Returns: (ok, message)
    """
    exe = find_soffice()
    if not exe:
        return False, "LibreOffice(soffice) 실행 파일을 찾지 못했습니다. (PATH 추가 또는 설치 경로 확인)"

    cmd = [str(exe), "--version"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=10).strip()
        #out을 space로 분리해서 0,1번째 요소만
        major_version, minor_version = out.split(" ")[0:2]
        # 일반적으로 "LibreOffice 24.x.x.x ..." 형태로 나옵니다.
        return True, major_version + "." + minor_version
    except subprocess.CalledProcessError as e:
        return False, f"soffice 호출 실패: {e.output.strip() if e.output else e}"
    except Exception as e:
        return False, f"soffice 버전 확인 중 오류: {e}"

def generate_cache_key(url: str) -> str:
    """URL을 기반으로 캐시 키 생성"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return f"aview:file:{url_hash}"

def extract_filename_from_url(url: str) -> str:
    """URL에서 파일명 추출"""
    parsed_url = urlparse(url)
    filename = unquote(parsed_url.path.split('/')[-1])
    return filename if filename else "unknown_file"

def extract_filename_from_headers(headers: dict) -> Optional[str]:
    """HTTP 응답 헤더에서 파일명 추출"""
    if 'content-disposition' not in headers:
        return None
    
    cd = headers['content-disposition']
    if 'filename=' not in cd:
        return None
    
    # filename="..." 또는 filename=... 형태 처리
    filename_part = cd.split('filename=')[-1]
    return filename_part.strip('"\'')

async def download_file_from_url(url: str) -> Tuple[bytes, str]:
    """
    외부 URL에서 파일 다운로드
    Returns: (파일 내용, 파일명)
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        
        # 파일명 추출 (헤더 우선, URL에서 추출은 후순위)
        filename = (
            extract_filename_from_headers(response.headers) 
            or extract_filename_from_url(url)
        )
        
        return response.content, filename

def validate_file_extension(filename: str) -> str:
    """파일 확장자 검증"""
    file_ext = Path(filename).suffix.lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"지원하지 않는 파일 형식: {file_ext}"
        )
    return file_ext

async def libreoffice_convert(
    input_path: Path, 
    output_dir: Path, 
    output_format: str,  # "pdf" 또는 "html"
    timeout: int = 60
) -> Path:
    """
    LibreOffice를 사용한 범용 문서 변환 (비동기)
    - 순수한 변환 로직만 담당
    - 표준 Exception 발생 (HTTPException 아님)
    - 상위에서 로깅과 예외 처리 담당
    
    Args:
        input_path: 입력 파일 경로
        output_dir: 출력 디렉토리 경로
        output_format: 변환 형식 ("pdf" 또는 "html")
        timeout: 변환 제한 시간 (초)
    
    Returns:
        변환된 파일 경로
        
    Raises:
        RuntimeError: LibreOffice 실행 파일을 찾을 수 없음
        FileNotFoundError: 입력 파일이 존재하지 않음
        subprocess.TimeoutExpired: 변환 시간 초과
        RuntimeError: 변환 실패 또는 출력 파일 없음
    """
    import asyncio
    import subprocess
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        raise RuntimeError("LibreOffice 실행 파일을 찾을 수 없습니다")
    
    # 입력 파일 존재 확인
    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일이 존재하지 않습니다: {input_path}")
    
    # 출력 디렉토리 생성
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # LibreOffice 임시 프로필 디렉토리
    LO_PROFILE_DIR = Path("/tmp/lo_profile")
    LO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    lo_profile = LO_PROFILE_DIR.resolve()
    
    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless", "--nologo", "--norestore", "--nolockcheck", "--nodefault", "--nocrashreport",
        f"-env:UserInstallation=file:///{lo_profile.as_posix()}",
        "--convert-to", output_format,
        "--outdir", str(output_dir),
        str(input_path)
    ]
    
    try:
        # 비동기 subprocess 실행
        loop = asyncio.get_event_loop()
        
        def run_subprocess():
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        result = await loop.run_in_executor(None, run_subprocess)
        
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice 변환 실패 (코드: {result.returncode}): {result.stderr}")
        
        # 변환된 파일 경로 생성
        output_filename = f"{input_path.stem}.{output_format}"
        output_path = output_dir / output_filename
        
        if not output_path.exists():
            raise RuntimeError(f"변환된 {output_format.upper()} 파일을 찾을 수 없습니다: {output_path}")
        
        return output_path
        
    except subprocess.TimeoutExpired:
        raise subprocess.TimeoutExpired(cmd, timeout)


def cleanup_old_cache_files(max_age_hours: int = 24):
    """오래된 캐시 파일 정리"""
    import time
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    cache_dir = Path(settings.CACHE_DIR)
    for cache_file in cache_dir.rglob("*"):
        if cache_file.is_file():
            file_age = current_time - cache_file.stat().st_mtime
            if file_age > max_age_seconds:
                try:
                    cache_file.unlink()
                except Exception:
                    pass  # 파일 삭제 실패 시 무시


async def download_and_cache_file(request: Request, url: str, settings: Config) -> Tuple[Path, str, bool]:
    """
    URL로 키를 만들어서 캐쉬에 있는지 체크 있으면 캐쉬를 없으면 URL에서 파일을 다운로드하고 캐시에 저장
    Returns: (파일 경로, 원본 파일명, cache_hit)
    """
    from app.core.utils import (  # 순환 import 방지
        generate_cache_key,
        validate_file_extension,
    )
    redis_client = request.app.state.redis
    stats_manager = request.app.state.stats_db

    # URL에서 파일명 추출 (URL 디코딩 적용)
    try:
        raw_filename = url.split('/')[-1].split('?')[0]  # 간단한 파일명 추출
        parsed_url = unquote(raw_filename) if raw_filename else "downloaded_file"  # URL 디코딩
        if not parsed_url:
            parsed_url = "downloaded_file"
    except(IndexError, AttributeError, TypeError):
        parsed_url = "downloaded_file"
    
    # 캐시 키 생성
    cache_key = generate_cache_key(url)
    
    # Redis에서 캐시된 파일 확인
    cached_filename = redis_client.get(cache_key)
    if cached_filename:
        if isinstance(cached_filename, bytes):
            cached_filename = cached_filename.decode('utf-8')
        file_ext = validate_file_extension(cached_filename)
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_path = Path(settings.CACHE_DIR) / f"{url_hash}{file_ext}"
        
        if cache_path.exists():
            logger.info(f"캐시에서 파일 사용: {cache_path}")
            return cache_path, cached_filename, True
    
    # 파일 다운로드
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"파일 다운로드 실패: HTTP {response.status}"
                    )
                
                # Content-Disposition에서 파일명 추출 시도
                original_filename = parsed_url
                content_disposition = response.headers.get('content-disposition')
                if content_disposition:
                    import re
                    filename_match = re.search(r'filename[*]?=([^;]+)', content_disposition)
                    if filename_match:
                        original_filename = filename_match.group(1).strip('"\'')
                
                # 파일 확장자 검증
                file_ext = validate_file_extension(original_filename)
                
                # 캐시 파일 경로 생성
                url_hash = hashlib.md5(url.encode()).hexdigest()
                cache_path = Path(settings.CACHE_DIR) / f"{url_hash}{file_ext}"
                
                # 캐시 디렉토리 생성
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 파일 다운로드 및 저장
                async with aiofiles.open(cache_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                
                # Redis에 파일명 캐시 (24시간)
                redis_client.setex(cache_key, 86400, original_filename)
                
                logger.info(f"파일 다운로드 완료: {cache_path}")
                return cache_path, original_filename, False
                
    except aiohttp.ClientError as e:
        logger.error(f"파일 다운로드 중 네트워크 오류-HTTP 클라이언트 오류: {str(e)}")
        stats_manager.log_error(
            'url', url, f'파일 다운로드 중 네트워크 오류-HTTP 클라이언트 오류: {str(e)}'
        )
        raise HTTPException(
            status_code=400,
            detail=f"파일 다운로드 중 네트워크 오류: {str(e)}"
        )
    except Exception as e:
        logger.error(f"파일 다운로드 중 예상치 못한 오류: {str(e)}")
        stats_manager.log_error(
            'url', url, f'파일 다운로드 중 예상치 못한 오류: {str(e)}'
        )
        raise HTTPException(
            status_code=500,
            detail=f"파일 다운로드 중 오류: {str(e)}"
        )


async def copy_and_cache_file(request: Request, path: str,  settings: Config) -> Tuple[Path, str, bool]:
    """
    로컬 파일을 캐시에 복사, 이미 캐쉬에 있으면 재사용
    Returns: (파일 경로, 원본 파일명, cache_hit)
    """
    from app.core.utils import (  # 순환 import 방지
        generate_cache_key,
        validate_file_extension,
    )
    redis_client = request.app.state.redis

    CACHE_DIR = Path(settings.CACHE_DIR)
    input_path = Path(path)
    
    if not input_path.exists() or not input_path.is_file():
        raise HTTPException(status_code=400, detail="지정된 경로에 파일이 존재하지 않습니다")
    
    filename = input_path.name
    file_ext = validate_file_extension(filename)
    
    # 캐시 키 생성 (파일 경로 기반)
    cache_key = generate_cache_key(str(input_path.resolve()))
    
    # Redis에서 캐시된 파일 정보 확인
    cached_info = redis_client.hgetall(cache_key)
    
    if cached_info:
        cached_path = Path(cached_info.get('path', ''))
        if cached_path.exists():
            return cached_path, cached_info.get('filename', 'unknown'), True

    # 캐시 파일 저장 (비동기)
    url_hash = hashlib.md5(str(input_path.resolve()).encode()).hexdigest()
    cache_file_path = CACHE_DIR / f"{url_hash}{file_ext}"
    
    # aiofiles를 사용한 비동기 파일 복사 (사용 가능한 경우)
    if AIOFILES_AVAILABLE:
        async with aiofiles.open(input_path, 'rb') as src:
            content = await src.read()
        async with aiofiles.open(cache_file_path, 'wb') as dst:
            await dst.write(content)
        
        # 파일 메타데이터 복사 (권한, 시간 등)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, shutil.copystat, input_path, cache_file_path)
    else:
        # aiofiles가 없으면 executor 사용
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, shutil.copy2, input_path, cache_file_path)
    
    # Redis에 캐시 정보 저장 (24시간 TTL)
    redis_client.hset(cache_key, mapping={
        'path': str(cache_file_path),
        'filename': filename,
        'url': str(input_path.resolve()),
        'size': cache_file_path.stat().st_size,
        'ext': file_ext
    })
    redis_client.expire(cache_key, 86400)  # 24시간

    return cache_file_path, filename, False

async def convert_to_pdf(input_path: Path, CONVERTED_DIR: Path) -> Path:
    """
    LibreOffice를 사용해 파일을 PDF로 변환 (비동기)
    Returns: 변환된 PDF 파일 경로
    """
    logger.info(f"PDF 변환 시작: {input_path}")
    
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
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        logger.error("LibreOffice 실행 파일을 찾을 수 없습니다")
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 실행 파일을 찾을 수 없습니다"
        )
    
    logger.info(f"LibreOffice 경로: {libre_office}")
    
    # 입력 파일 존재 확인
    if not input_path.exists():
        logger.error(f"입력 파일이 존재하지 않습니다: {input_path}")
        raise HTTPException(
            status_code=500,
            detail=f"입력 파일이 존재하지 않습니다: {input_path}"
        )
    
    # 출력 디렉토리 생성
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"출력 디렉토리: {CONVERTED_DIR}")
    # LibreOffice 임시 프로필 디렉토리 (Linux/Windows 모두 문제 없음)
    LO_PROFILE_DIR = Path("/tmp/lo_profile")  # Linux/Windows 모두 문제 없음
    LO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    lo_profile = LO_PROFILE_DIR.resolve()
    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless", "--nologo", "--norestore", "--nolockcheck", "--nodefault","--nocrashreport",
        f"-env:UserInstallation=file:///{lo_profile.as_posix()}",
        "--convert-to", "pdf",
        "--outdir", str(CONVERTED_DIR),
        str(input_path)
    ]
    
    logger.info(f"LibreOffice 명령: {' '.join(cmd)}")
    
    try:
        # 플랫폼에 관계없이 안정적인 subprocess 실행을 위해 executor 사용
        import subprocess
        loop = asyncio.get_event_loop()
        
        def run_subprocess():
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        result = await loop.run_in_executor(None, run_subprocess)
        
        # 결과 로깅
        if result.stdout:
            logger.info(f"LibreOffice stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"LibreOffice stderr: {result.stderr}")
        
        logger.info(f"LibreOffice 프로세스 종료 코드: {result.returncode}")
        
        if result.returncode != 0:
            error_msg = f"LibreOffice 변환 실패 (코드: {result.returncode}): {result.stderr}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
        
        # 파일 생성 확인
        if not pdf_path.exists():
            logger.error(f"변환된 PDF 파일을 찾을 수 없습니다: {pdf_path}")
            # 디렉토리 내용 확인
            existing_files = list(CONVERTED_DIR.glob("*"))
            logger.info(f"변환 디렉토리 내 파일들: {existing_files}")
            
            raise HTTPException(
                status_code=500,
                detail=f"변환된 PDF 파일을 찾을 수 없습니다: {pdf_path}"
            )
        
        logger.info(f"PDF 변환 성공: {input_path} -> {pdf_path}")
        return pdf_path
        
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice 변환 시간 초과")
        raise HTTPException(
            status_code=500,
            detail="문서 변환 시간이 초과되었습니다"
        )
    except Exception as e:
        logger.error(f"PDF 변환 중 예상치 못한 오류: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류 발생: {str(e)}"
        )


def convert_with_libreoffice(input_path: Path, html_path: Path) -> Path:
    """
    LibreOffice를 사용한 변환 (백업용)
    """
    CONVERTED_DIR = html_path.parent
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 실행 파일을 찾을 수 없습니다"
        )

    LO_PROFILE_DIR = Path("/tmp/lo_profile")  # Linux/Windows 모두 문제 없음
    LO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    lo_profile = LO_PROFILE_DIR.resolve()

    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless", "--nologo", "--norestore", "--nolockcheck", "--nodefault","--nocrashreport",
        f"-env:UserInstallation=file:///{lo_profile.as_posix()}",
        "--convert-to", "html",
        "--outdir", str(CONVERTED_DIR),
        str(input_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"LibreOffice 변환 실패: {result.stderr}"
            )
        
        if not html_path.exists():
            raise HTTPException(
                status_code=500,
                detail="변환된 HTML 파일을 찾을 수 없습니다"
            )
            
        return html_path
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="문서 변환 시간이 초과되었습니다"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류 발생: {str(e)}"
        )


async def convert_with_libreoffice_async(input_path: Path, html_path: Path) -> Path:
    """
    LibreOffice를 사용한 비동기 변환
    """
    CONVERTED_DIR = Path(settings.CONVERTED_DIR)
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 실행 파일을 찾을 수 없습니다"
        )
    LO_PROFILE_DIR = Path("/tmp/lo_profile")  # Linux/Windows 모두 문제 없음
    LO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    lo_profile = LO_PROFILE_DIR.resolve()
    logger.info(f"lo_profile 경로: {lo_profile}")    
    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless", "--nologo", "--norestore", "--nolockcheck", "--nodefault","--nocrashreport",
        f"-env:UserInstallation=file:///{lo_profile.as_posix()}",
        "--convert-to", "pdf",
        "--outdir", str(CONVERTED_DIR),
        str(input_path)
    ]
    
    try:
        # 플랫폼에 관계없이 안정적인 subprocess 실행을 위해 executor 사용
        import subprocess
        loop = asyncio.get_event_loop()
        
        def run_subprocess():
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        result = await loop.run_in_executor(None, run_subprocess)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"LibreOffice 변환 실패: {result.stderr}"
            )
        
        if not html_path.exists():
            raise HTTPException(
                status_code=500,
                detail="변환된 HTML 파일을 찾을 수 없습니다"
            )
            
        return html_path
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="문서 변환 시간이 초과되었습니다"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"문서 변환 중 오류 발생: {str(e)}"
        )



def convert_pdf_to_html(pdf_path: Path, html_path: Path, original_filename:str = None)->Path:
    '''
    pdf를 html로 감싸서 보여준다. tempalte viewer/pdf_html
    '''
    """
    PDF 파일을 HTML로 감싸서 브라우저에서 볼 수 있도록 함
    브라우저의 내장 PDF 뷰어를 사용
    Returns: 변환된 HTML 파일 경로
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        
        # PDF 파일 정보 추출
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        # PDF 파일의 웹 서버 URL 생성 (정적 파일 서빙용)
        pdf_filename = pdf_path.name
        pdf_url = f"/aview/pdf/{pdf_filename}"  # aview_routes.py의 /pdf/{filename} 엔드포인트 사용
        
        # PDF 메타데이터 추출 시도 (선택적)
        pdf_info = {}
        try:
            # PyPDF2나 pdfplumber가 있다면 사용
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                pdf_info['pages'] = len(reader.pages)
                if reader.metadata:
                    pdf_info['title'] = reader.metadata.get('/Title', '')
                    pdf_info['author'] = reader.metadata.get('/Author', '')
                    pdf_info['subject'] = reader.metadata.get('/Subject', '')
                    pdf_info['creator'] = reader.metadata.get('/Creator', '')
        except ImportError:
            logger.info("PyPDF2가 설치되지 않아 PDF 메타데이터를 추출할 수 없습니다")
            pdf_info['pages'] = 'Unknown'
        except Exception as e:
            logger.warning(f"PDF 메타데이터 추출 실패: {e}")
            pdf_info['pages'] = 'Unknown'
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터 추가
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/pdf.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else pdf_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            pdf_url=pdf_url,  # 웹 서버 URL 사용
            pdf_filename=pdf_filename,
            file_size=file_size,
            file_size_mb=round(file_size_mb, 2),
            pdf_info=pdf_info
        )
        # HTML 파일로 저장 (UTF-8 인코딩)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"PDF를 HTML로 변환 완료: {pdf_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"PDF를 HTML로 변환 실패: {str(e)}")
        # 실패 시 기본 구현 사용
        return convert_basic_pdf_to_html(pdf_path, html_path, original_filename)

def convert_basic_pdf_to_html(pdf_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    기본 PDF HTML 변환 (메타데이터 없이)
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        
        # 기본 파일 정보
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        pdf_filename = pdf_path.name
        
        # PDF 파일의 웹 서버 URL 생성
        pdf_url = f"/pdf/{pdf_filename}"
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/pdf.html')
        
        # 템플릿 렌더링 (기본값들)
        display_filename = original_filename if original_filename else pdf_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            pdf_url=pdf_url,  # 웹 서버 URL 사용
            pdf_filename=pdf_filename,
            file_size=file_size,
            file_size_mb=round(file_size_mb, 2),
            pdf_info={'pages': 'Unknown'}
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"PDF를 기본 HTML로 변환 완료: {pdf_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"기본 PDF HTML 변환 실패: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"PDF 변환 중 오류 발생: {str(e)}"
        )
def convert_csv_to_html(csv_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    CSV 파일을 pandas를 사용해서 HTML로 변환 (한글 인코딩 문제 해결)
    Jinja2 템플릿 사용
    Returns: 변환된 HTML 파일 경로
    """
    try:
        import pandas as pd
        from jinja2 import Environment, FileSystemLoader
        
        # 여러 인코딩을 시도해서 CSV 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        df = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_path, encoding=encoding)
                logger.info(f"CSV 파일을 {encoding} 인코딩으로 성공적으로 읽었습니다: {csv_path}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if df is None:
            raise ValueError("CSV 파일을 읽을 수 없습니다. 지원되는 인코딩이 없습니다.")
        
        # DataFrame을 HTML 테이블로 변환 (한글 지원 개선)
        # pandas to_html 사용하되 escape=False로 설정하여 한글 문제 해결
        table_html = df.to_html(
            table_id="csvTable",
            classes="csv-table table table-striped table-hover",
            escape=False,
            index=False,
            border=0
        )
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template('viewer/csv.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else csv_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            row_count=len(df),
            col_count=len(df.columns),
            table_html=table_html
        )
        
        # HTML 파일로 저장 (UTF-8 인코딩)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"CSV를 HTML로 변환 완료: {csv_path} -> {html_path}")
        return html_path
        
    except ImportError:
        # pandas가 없는 경우 LibreOffice 사용
        logger.warning("pandas가 설치되지 않아 LibreOffice를 사용합니다")
        return convert_with_libreoffice(csv_path, html_path)
    except Exception as e:
        logger.error(f"CSV to HTML 변환 실패: {str(e)}")
        # 실패 시 LibreOffice 사용
        return convert_with_libreoffice(csv_path, html_path)


def convert_txt_to_html(txt_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    텍스트 파일을 HTML로 변환 (한글 인코딩 문제 해결)
    Jinja2 템플릿 사용
    Returns: 변환된 HTML 파일 경로
    """
    try:
        import html

        from jinja2 import Environment, FileSystemLoader
        
        # 여러 인코딩을 시도해서 텍스트 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin-1']
        content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(txt_path, 'r', encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                logger.info(f"텍스트 파일을 {encoding} 인코딩으로 성공적으로 읽었습니다: {txt_path}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise ValueError("텍스트 파일을 읽을 수 없습니다. 지원되는 인코딩이 없습니다.")
        
        # HTML 특수문자 이스케이프
        escaped_content = html.escape(content)
        
        # 줄바꿈을 <br/> 태그로 변환
        escaped_content = escaped_content.replace('\n', '<br/>')
        
        # 라인 수 계산 (원본 기준)
        lines = content.split('\n')
        line_count = len(lines)
        
        # 라인 넘버링 처리 (50줄 이하만)
        show_line_numbers = line_count <= 50
        line_numbers = None
        
        if show_line_numbers:
            line_numbers = '<br/>'.join(str(i+1) for i in range(line_count))
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터 추가
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/txt.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else txt_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            line_count=line_count,
            char_count=len(content),
            encoding=used_encoding,
            content=escaped_content,
            show_line_numbers=show_line_numbers,
            line_numbers=line_numbers
        )
        
        # HTML 파일로 저장 (UTF-8 인코딩)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"TXT를 HTML로 변환 완료: {txt_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"TXT to HTML 변환 실패: {str(e)}")
        # 실패 시 LibreOffice 사용
        return convert_with_libreoffice(txt_path, html_path)


def convert_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    이미지 파일을 HTML로 변환 (Viewer.js 기반 뷰어)
    Returns: 변환된 HTML 파일 경로
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from PIL import Image
        
        # 이미지 정보 추출
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format_name = img.format
                mode = img.mode
                
                # EXIF 데이터 추출 (있는 경우)
                exif_data = {}
                if hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        # 주요 EXIF 태그들
                        exif_tags = {
                            271: 'Camera Make', 272: 'Camera Model', 
                            306: 'DateTime', 33434: 'Exposure Time',
                            33437: 'F Number', 34855: 'ISO Speed'
                        }
                        for tag_id, value in exif.items():
                            if tag_id in exif_tags:
                                exif_data[exif_tags[tag_id]] = str(value)
        except Exception as e:
            logger.warning(f"이미지 정보 추출 실패: {e}")
            width = height = 0
            format_name = "Unknown"
            mode = "Unknown"
            exif_data = {}
        
        # 파일 크기
        file_size = image_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        # 이미지 파일의 상대 경로 생성 (정적 파일 서빙용)
        # 실제 구현에서는 이미지 파일을 정적 디렉토리로 복사하거나 링크 생성
        image_filename = image_path.name
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template('viewer/image.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else image_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            image_path=str(image_path),  # 절대 경로
            image_filename=image_filename,
            width=width,
            height=height,
            format=format_name,
            mode=mode,
            file_size=file_size,
            file_size_mb=round(file_size_mb, 2),
            exif_data=exif_data
        )
        # logger.debug(f"이미지 View 변환정보: {html_content}")
        # HTML 파일로 저장 (UTF-8 인코딩)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"이미지를 HTML로 변환 완료: {image_path} -> {html_path}")
        return html_path
        
    except ImportError:
        # PIL이 없는 경우 기본 구현
        logger.warning("Pillow가 설치되지 않아 기본 이미지 뷰어를 사용합니다")
        return convert_basic_image_to_html(image_path, html_path, original_filename)
    except Exception as e:
        logger.error(f"이미지를 HTML로 변환 실패: {str(e)}")
        # 실패 시 LibreOffice 사용
        return convert_with_libreoffice(image_path, html_path)


def convert_basic_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    기본 이미지 HTML 변환 (PIL 없이)
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        
        # 기본 파일 정보
        file_size = image_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        image_filename = image_path.name
        
        # Jinja2 템플릿 로드
        current_dir = Path(__file__).parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template('viewer/image.html')
        
        # 템플릿 렌더링 (기본값들)
        display_filename = original_filename if original_filename else image_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            image_path=str(image_path),
            image_filename=image_filename,
            width=0,
            height=0,
            format="Unknown",
            mode="Unknown",
            file_size=file_size,
            file_size_mb=round(file_size_mb, 2),
            exif_data={}
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"이미지를 기본 HTML로 변환 완료: {image_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"기본 이미지 HTML 변환 실패: {str(e)}")
        return convert_with_libreoffice(image_path, html_path)


def convert_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    마크다운 파일을 HTML로 변환
    markdown 라이브러리와 Pygments를 사용한 고급 렌더링
    Returns: 변환된 HTML 파일 경로  
    """
    try:
        import markdown

        # from markdown.extensions import codehilite, tables, toc, fenced_code
        from jinja2 import Environment, FileSystemLoader
        
        logger.info(f"마크다운 변환 시작: {md_path}")
        
        # 여러 인코딩을 시도해서 마크다운 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin-1']
        content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(md_path, 'r', encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                logger.info(f"마크다운 파일을 {encoding} 인코딩으로 성공적으로 읽었습니다: {md_path}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise ValueError("마크다운 파일을 읽을 수 없습니다. 지원되는 인코딩이 없습니다.")
        
        # 마크다운 확장 기능 설정
        extensions = [
            'codehilite',       # 코드 구문 강조
            'tables',           # 테이블 지원
            'toc',              # 목차 생성
            'fenced_code',      # 펜스드 코드 블록
            'nl2br',            # 줄바꿈을 <br>로 변환
            'sane_lists',       # 리스트 처리 개선
            'smarty',           # 스마트 따옴표/대시
        ]
        
        # 확장 기능 설정
        extension_configs = {
            'codehilite': {
                'css_class': 'highlight',
                'use_pygments': True,
                'noclasses': False,
            },
            'toc': {
                'toc_depth': 6,
                'permalink': True,
                'permalink_title': '이 제목으로 링크',
            }
        }
        
        # 마크다운을 HTML로 변환
        md = markdown.Markdown(
            extensions=extensions,
            extension_configs=extension_configs
        )
        
        html_content_body = md.convert(content)
        toc_html = getattr(md, 'toc', '')
        
        # 메타데이터 추출 (있는 경우)
        meta = getattr(md, 'Meta', {})
        
        # 파일 정보
        file_size = md_path.stat().st_size
        file_size_kb = file_size / 1024
        line_count = len(content.split('\n'))
        char_count = len(content)
        
        # 헤딩 개수 계산
        headings = re.findall(r'^#{1,6}\s+(.+)$', content, re.MULTILINE)
        heading_count = len(headings)
        
        
        # 코드 강조 스타일 (GitHub 유사한 스타일)
        try:
            formatter = HtmlFormatter(style='vs', cssclass='highlight')  # vs 스타일이 GitHub과 유사
        except Exception:
            # 기본 스타일도 실패하면 스타일 없이
            formatter = HtmlFormatter(cssclass='highlight')
        syntax_css = formatter.get_style_defs('.highlight')
        
        # Jinja2 템플릿 로드
        template_dir = settings.TEMPLATE_DIR
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터 추가
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/markdown.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else md_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            markdown_content=html_content_body,
            toc_content=toc_html,
            has_toc=bool(toc_html.strip()),
            syntax_css=syntax_css,
            meta=meta,
            file_size=file_size,
            file_size_kb=round(file_size_kb, 2),
            line_count=line_count,
            char_count=char_count,
            heading_count=heading_count,
            encoding=used_encoding
        )
        
        # HTML 파일로 저장 (UTF-8 인코딩)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"마크다운을 HTML로 변환 완료: {md_path} -> {html_path}")
        return html_path
        
    except ImportError as e:
        # markdown 라이브러리가 없는 경우
        logger.warning(f"마크다운 라이브러리가 없습니다: {e}")
        return convert_basic_md_to_html(md_path, html_path, original_filename)
    except Exception as e:
        logger.error(f"마크다운을 HTML로 변환 실패: {str(e)}")
        logger.error(f"예외 타입: {type(e).__name__}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        # 실패 시 LibreOffice 사용
        return convert_with_libreoffice(md_path, html_path)


def convert_basic_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    기본 마크다운 HTML 변환 (markdown 라이브러리 없이)
    """
    try:
        import html

        from jinja2 import Environment, FileSystemLoader
        
        # 마크다운 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig', 'latin-1']
        content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(md_path, 'r', encoding=encoding) as f:
                    content = f.read()
                used_encoding = encoding
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            raise ValueError("마크다운 파일을 읽을 수 없습니다.")
        
        # 기본적인 마크다운 처리 (제한적)
        escaped_content = html.escape(content)
        escaped_content = escaped_content.replace('\n', '<br/>')
        
        # 템플릿 렌더링
        current_dir = Path(__file__).parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template('viewer/markdown.html')
        
        display_filename = original_filename if original_filename else md_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            markdown_content=f'<pre><code>{escaped_content}</code></pre>',
            toc_content='',
            has_toc=False,
            syntax_css='',
            meta={},
            file_size=md_path.stat().st_size,
            file_size_kb=round(md_path.stat().st_size / 1024, 2),
            line_count=len(content.split('\n')),
            char_count=len(content),
            heading_count=0,
            encoding=used_encoding
        )
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"기본 마크다운을 HTML로 변환 완료: {md_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"기본 마크다운 HTML 변환 실패: {str(e)}")
        return convert_with_libreoffice(md_path, html_path)


async def convert_to_html(request: Request, input_file_path: str, original_filename: str = None) -> Path:
    """
    LibreOffice를 사용해 파일을 HTML로 변환 (비동기)
    특정 파일 타입은 전용 변환 함수 사용 (한글 인코딩 문제 해결)
    Returns: 변환된 HTML 파일 경로
    """
    input_path = Path(input_file_path)
    # 이미 HTML인 경우 그대로 반환
    if input_path.suffix.lower() in {'.html', '.htm'}:
        return input_path
    
    CONVERTED_DIR = Path(settings.CONVERTED_DIR)
    # 변환된 파일 경로
    html_filename = f"{input_path.stem}.html"
    html_path = CONVERTED_DIR / html_filename
    
    # 이미 변환된 파일이 있으면 반환
    if html_path.exists():
        return html_path
    
    # 파일 타입별 전용 변환 함수 사용 (이들은 동기이므로 executor 사용)
    if input_path.suffix.lower() == '.csv':
        return await asyncio.get_event_loop().run_in_executor(
            None, convert_csv_to_html, input_path, html_path, original_filename
        )
    elif input_path.suffix.lower() == '.txt':
        return await asyncio.get_event_loop().run_in_executor(
            None, convert_txt_to_html, input_path, html_path, original_filename
        )
    elif input_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}:
        return await asyncio.get_event_loop().run_in_executor(
            None, convert_image_to_html, input_path, html_path, original_filename
        )
    elif input_path.suffix.lower() == '.md':
        return await asyncio.get_event_loop().run_in_executor(
            None, convert_md_to_html, input_path, html_path, original_filename
        )
    elif input_path.suffix.lower() == '.pdf':
        return await asyncio.get_event_loop().run_in_executor(
            None, convert_pdf_to_html, input_path, html_path, original_filename
        )
    # 오피스 문서를 view하는 경우임
    # HTML 경로의 확장자를 PDF로 변경
    pdf_path = html_path.with_suffix('.pdf')
    converted_path =  await convert_with_libreoffice_async(input_path, pdf_path)
    # 여기서 리턴하면 이것은 pdf
    logger.info(f"오피스문서 Libre로 변환된 pdf: {converted_path}")
    logger.info(f"HTML 경로: {html_path}, PDF 경로: {pdf_path}, 변환된 경로: {converted_path}, original_filename: {original_filename}")
    # html을 리턴한다.
    return await asyncio.get_event_loop().run_in_executor(
        None, convert_pdf_to_html, converted_path, html_path, original_filename
    )
    # return converted_path

# async def convert_to_html(request: Request, input_file_path: str, original_filename: str = None) -> Path:
#     """
#     LibreOffice를 사용해 파일을 HTML로 변환 (비동기)
#     특정 파일 타입은 전용 변환 함수 사용 (한글 인코딩 문제 해결)
#     Returns: 변환된 HTML 파일 경로
#     """
#     input_path = Path(input_file_path)
#     # 이미 HTML인 경우 그대로 반환
#     if input_path.suffix.lower() in {'.html', '.htm'}:
#         return input_path
    
#     CONVERTED_DIR = Path(settings.CONVERTED_DIR)
#     # 변환된 파일 경로
#     html_filename = f"{input_path.stem}.html"
#     html_path = CONVERTED_DIR / html_filename
    
#     # 이미 변환된 파일이 있으면 반환
#     if html_path.exists():
#         return html_path
    
#     # 파일 타입별 전용 변환 함수 사용 (이들은 동기이므로 executor 사용)
#     if input_path.suffix.lower() == '.csv':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, convert_csv_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.txt':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, convert_txt_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}:
#         return await asyncio.get_event_loop().run_in_executor(
#             None, convert_image_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.md':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, convert_md_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.pdf':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, convert_pdf_to_html, input_path, html_path, original_filename
#         )
#     # 오피스 문서를 view하는 경우임
#     # HTML 경로의 확장자를 PDF로 변경
#     pdf_path = html_path.with_suffix('.pdf')
#     converted_path =  await convert_with_libreoffice_async(input_path, pdf_path)
#     # 여기서 리턴하면 이것은 pdf
#     logger.info(f"오피스문서 Libre로 변환된 pdf: {converted_path}")
#     logger.info(f"HTML 경로: {html_path}, PDF 경로: {pdf_path}, 변환된 경로: {converted_path}, original_filename: {original_filename}")
#     # html을 리턴한다.
#     return await asyncio.get_event_loop().run_in_executor(
#         None, convert_pdf_to_html, converted_path, html_path, original_filename
#     )
#     # return converted_path
