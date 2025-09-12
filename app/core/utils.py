"""
A-View 유틸리티 함수들
- 간단한 헬퍼 함수들만 포함
- 복잡한 변환 로직은 convert_lib, view_lib 참조
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.file_ext_definition import (
    SUPPORTED_EXTENSIONS
)

logger = get_logger(__name__)

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