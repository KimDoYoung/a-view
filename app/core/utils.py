"""
A-View 유틸리티 함수들
- 간단한 헬퍼 함수들만 포함
- 복잡한 변환 로직은 convert_lib, view_lib 참조
"""
import asyncio
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, unquote

import aiofiles
import aiohttp
import httpx
from fastapi import HTTPException, Request

from app.core.config import Config, settings
from app.core.logger import get_logger
from app.domain.file_ext_definition import (
    SUPPORTED_EXTENSIONS
)

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
    from app.core.utils import generate_cache_key, validate_file_extension  # 순환 import 방지
    redis_client = request.app.state.redis
    stats_manager = request.app.state.stats_db

    # URL에서 파일명 추출 (URL 디코딩 적용)
    try:
        raw_filename = url.split('/')[-1].split('?')[0]  # 간단한 파일명 추출
        parsed_url = unquote(raw_filename) if raw_filename else "downloaded_file"  # URL 디코딩
        if not parsed_url:
            parsed_url = "downloaded_file"
    except:
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
    from app.core.utils import generate_cache_key, validate_file_extension  # 순환 import 방지
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
