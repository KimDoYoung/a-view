"""
A-View 유틸리티 함수들
- 파일 다운로드 및 캐시 관리
- LibreOffice 문서 변환
- Redis 캐시 작업
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import httpx
import redis
from fastapi import HTTPException

from app.config import settings, Config
from app.logger import get_logger

logger = get_logger(__name__)

# LibreOffice 지원 확장자 및 MIME 타입
SUPPORTED_EXTENSIONS = {
    '.doc', '.docx', '.odt', '.rtf',  # 문서
    '.xls', '.xlsx', '.ods', '.csv',   # 스프레드시트  
    '.ppt', '.pptx', '.odp',          # 프레젠테이션
    '.pdf',                            # PDF (이미 변환된 파일)
    '.txt',
    '.md',
    '.html', '.htm'
}
# pdf나 html로 변환가능한 확장자
CONVERTABLE_EXTENSIONS =  {
    '.doc', '.docx', '.odt', '.rtf',
    '.xls', '.xlsx', '.ods', '.csv',
    '.ppt', '.pptx', '.odp'
}

def get_redis(request):
    return getattr(request.app.state, "redis", None)

def get_templates(request):
    return request.app.state.templates

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
        # 일반적으로 "LibreOffice 24.x.x.x ..." 형태로 나옵니다.
        return True, out
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

async def download_and_cache_file(redis_client: redis.Redis, url: str,  settings: Config) -> Tuple[Path, str]:
    """
    외부 URL에서 파일을 다운로드하고 캐시에 저장, 이미 캐쉬에 있으면 재사용
    Returns: (파일 경로, 원본 파일명)
    """
    CACHE_DIR = Path(settings.CACHE_DIR)
    cache_key = generate_cache_key(url)
    
    # Redis에서 캐시된 파일 정보 확인
    cached_info = redis_client.hgetall(cache_key)
    
    if cached_info:
        cached_path = Path(cached_info.get('path', ''))
        if cached_path.exists():
            return cached_path, cached_info.get('filename', 'unknown')
    
    # 파일 다운로드
    file_content, filename = await download_file_from_url(url)
    
    # 파일 확장자 검증
    file_ext = validate_file_extension(filename)
    
    # 캐시 파일 저장
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_file_path = CACHE_DIR / f"{url_hash}{file_ext}"
    cache_file_path.write_bytes(file_content)
    
    # Redis에 캐시 정보 저장 (24시간 TTL)
    redis_client.hset(cache_key, mapping={
        'path': str(cache_file_path),
        'filename': filename,
        'url': url,
        'size': len(file_content),
        'ext': file_ext
    })
    redis_client.expire(cache_key, 86400)  # 24시간
    
    return cache_file_path, filename

async def copy_and_cache_file(path: str, redis_client: redis.Redis, settings: Config) -> Tuple[Path, str]:
    """
    로컬 파일을 캐시에 복사, 이미 캐쉬에 있으면 재사용
    Returns: (파일 경로, 원본 파일명)
    """
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
            return cached_path, cached_info.get('filename', 'unknown')
    
    # 캐시 파일 저장
    url_hash = hashlib.md5(str(input_path.resolve()).encode()).hexdigest()
    cache_file_path = CACHE_DIR / f"{url_hash}{file_ext}"
    shutil.copy2(input_path, cache_file_path)
    
    # Redis에 캐시 정보 저장 (24시간 TTL)
    redis_client.hset(cache_key, mapping={
        'path': str(cache_file_path),
        'filename': filename,
        'url': str(input_path.resolve()),
        'size': cache_file_path.stat().st_size,
        'ext': file_ext
    })
    redis_client.expire(cache_key, 86400)  # 24시간
    
    return cache_file_path, filename

def convert_to_pdf(input_path: Path, CONVERTED_DIR: Path) -> Path:
    """
    LibreOffice를 사용해 파일을 PDF로 변환
    Returns: 변환된 PDF 파일 경로
    """
    # 이미 PDF인 경우 그대로 반환
    if input_path.suffix.lower() == '.pdf':
        return input_path
    
    # 변환된 파일 경로
    pdf_filename = f"{input_path.stem}.pdf"
    pdf_path = CONVERTED_DIR / pdf_filename
    
    # 이미 변환된 파일이 있으면 반환
    if pdf_path.exists():
        return pdf_path
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 실행 파일을 찾을 수 없습니다"
        )
    
    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless",
        "--convert-to", "pdf",
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
        
        if not pdf_path.exists():
            raise HTTPException(
                status_code=500,
                detail="변환된 PDF 파일을 찾을 수 없습니다"
            )
            
        return pdf_path
        
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

def convert_to_html(input_path: Path, CONVERTED_DIR: Path) -> Path:
    """
    LibreOffice를 사용해 파일을 HTML로 변환
    Returns: 변환된 HTML 파일 경로
    """
    # 이미 HTML인 경우 그대로 반환
    if input_path.suffix.lower() in {'.html', '.htm'}:
        return input_path
    
    # 변환된 파일 경로
    html_filename = f"{input_path.stem}.html"
    html_path = CONVERTED_DIR / html_filename
    
    # 이미 변환된 파일이 있으면 반환
    if html_path.exists():
        return html_path
    
    # LibreOffice 실행 파일 찾기
    libre_office = find_soffice()
    if not libre_office:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice 실행 파일을 찾을 수 없습니다"
        )
    
    # LibreOffice 변환 명령
    cmd = [
        str(libre_office),
        "--headless",
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


def cleanup_old_cache_files(max_age_hours: int = 24):
    """오래된 캐시 파일 정리"""
    from app.config import settings
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

async def get_cached_pdf(redis_client: redis.Redis, url: str,  settings: Config) -> Tuple[Path, str]:
    """
    URL에서 파일을 다운로드하고 PDF로 변환하여 반환
    Returns: (PDF 파일 경로, 원본 파일명)
    """
    # 파일 다운로드 및 캐시
    file_path, original_filename = await download_and_cache_file(redis_client, url, settings)
    
    # PDF로 변환
    converted_dir = Path(settings.CONVERTED_DIR)
    pdf_path = convert_to_pdf(file_path, converted_dir)
    
    return pdf_path, original_filename

async def url_download_and_convert(redis_client: redis.Redis, url: str, output_format: str) -> str:
    """
    URL에서 파일을 다운로드하고 지정된 형식으로 변환
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    converted_dir = Path(settings.CONVERTED_DIR)
    if output_format.lower().endswith('pdf'):
        file_path, original_filename = await download_and_cache_file(redis_client, url, settings)
        output_path = convert_to_pdf(file_path, converted_dir)

    elif output_format.lower().endswith('html'):
        file_path, original_filename = await download_and_cache_file(redis_client, url, settings)
        output_path = convert_to_html(file_path, converted_dir)
    
    logger.info(f"url :{url} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    url = f"http://{settings.HOST}:{settings.PORT}/aview/{output_format}/{output_path.name}"
    logger.info(f"변환된 파일 URL: {url}")
    return url


async def local_file_copy_and_convert(redis_client: redis.Redis,path: str, output_format: str) -> str:
    """
    로컬 파일을 지정된 형식으로 변환
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    converted_dir = Path(settings.CONVERTED_DIR)
    if output_format.lower().endswith('pdf'):
        file_path, original_filename = await copy_and_cache_file(path, redis_client, settings)
        output_path = convert_to_pdf(file_path, converted_dir)

    elif output_format.lower().endswith('html'):
        file_path, original_filename = await copy_and_cache_file(path, redis_client, settings)
        output_path = convert_to_html(file_path, converted_dir)

    logger.info(f"path :{path} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    url = f"http://{settings.HOST}:{settings.PORT}/aview/{output_format.lower()}/{output_path.name}"
    logger.info(f"변환된 파일 URL: {url}")
    return url