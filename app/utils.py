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

from app.config import Config

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

async def download_and_cache_file(url: str, redis_client: redis.Redis, settings: Config) -> Tuple[Path, str]:
    """
    외부 URL에서 파일을 다운로드하고 캐시에 저장
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

async def get_cached_pdf(url: str, redis_client: redis.Redis, settings: Config) -> Tuple[Path, str]:
    """
    URL에서 파일을 다운로드하고 PDF로 변환하여 반환
    Returns: (PDF 파일 경로, 원본 파일명)
    """
    # 파일 다운로드 및 캐시
    file_path, original_filename = await download_and_cache_file(url, redis_client, settings)
    
    # PDF로 변환
    converted_dir = Path(settings.CONVERTED_DIR)
    pdf_path = convert_to_pdf(file_path, converted_dir)
    
    return pdf_path, original_filename

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