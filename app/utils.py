"""
A-View 유틸리티 함수들
- 파일 다운로드 및 캐시 관리
- LibreOffice 문서 변환
- Redis 캐시 작업
"""

import hashlib
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import httpx
import redis
from fastapi import HTTPException

# LibreOffice 지원 확장자 및 MIME 타입
SUPPORTED_EXTENSIONS = {
    '.doc', '.docx', '.odt', '.rtf',  # 문서
    '.xls', '.xlsx', '.ods', '.csv',   # 스프레드시트  
    '.ppt', '.pptx', '.odp',          # 프레젠테이션
    '.pdf'                            # PDF (이미 변환된 파일)
}

OFFICE_MIME_TYPES = {
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel', 
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'application/pdf',
    'text/csv'
}

# 캐시 디렉토리 설정
CACHE_DIR = Path("/tmp/aview_cache")
CONVERTED_DIR = CACHE_DIR / "converted"

def init_cache_directories():
    """캐시 디렉토리 초기화"""
    CACHE_DIR.mkdir(exist_ok=True)
    CONVERTED_DIR.mkdir(exist_ok=True)

def check_libreoffice() -> bool:
    """LibreOffice 설치 및 실행 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["libreoffice", "--version"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False

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

async def download_and_cache_file(url: str, redis_client: redis.Redis) -> Tuple[Path, str]:
    """
    외부 URL에서 파일을 다운로드하고 캐시에 저장
    Returns: (파일 경로, 원본 파일명)
    """
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

def convert_to_pdf(input_path: Path) -> Path:
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
    
    # LibreOffice 변환 명령
    cmd = [
        "libreoffice",
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

async def get_cached_pdf(url: str, redis_client: redis.Redis) -> Tuple[Path, str]:
    """
    URL에서 파일을 다운로드하고 PDF로 변환하여 반환
    Returns: (PDF 파일 경로, 원본 파일명)
    """
    # 파일 다운로드 및 캐시
    file_path, original_filename = await download_and_cache_file(url, redis_client)
    
    # PDF로 변환
    pdf_path = convert_to_pdf(file_path)
    
    return pdf_path, original_filename

def cleanup_old_cache_files(max_age_hours: int = 24):
    """오래된 캐시 파일 정리"""
    import time
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    
    for cache_file in CACHE_DIR.rglob("*"):
        if cache_file.is_file():
            file_age = current_time - cache_file.stat().st_mtime
            if file_age > max_age_seconds:
                try:
                    cache_file.unlink()
                except Exception:
                    pass  # 파일 삭제 실패 시 무시