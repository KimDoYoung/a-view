"""
Convert Library
PDF 변환 관련 기능들을 모아놓은 라이브러리
"""

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Tuple

import aiofiles
import aiohttp
import redis
from fastapi import HTTPException

from app.core.config import Config, settings
from app.core.logger import logger


async def convert_to_pdf(input_path: Path, CONVERTED_DIR: Path) -> Path:
    """
    파일을 PDF로 변환
    LibreOffice를 사용하여 다양한 문서 포맷을 PDF로 변환
    """
    from app.core.utils import find_soffice  # 순환 import 방지
    
    # 이미 PDF인 경우 그대로 반환
    if input_path.suffix.lower() == '.pdf':
        return input_path
    
    pdf_filename = f"{input_path.stem}.pdf"
    pdf_path = CONVERTED_DIR / pdf_filename
    
    # 이미 변환된 파일이 있으면 반환
    if pdf_path.exists():
        return pdf_path
    
    # LibreOffice 실행 파일 경로 찾기
    soffice_path = find_soffice()
    if not soffice_path:
        raise HTTPException(
            status_code=500,
            detail="LibreOffice가 설치되어 있지 않습니다"
        )
    
    # 변환된 파일 저장을 위한 디렉토리 생성
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # LibreOffice 명령어 실행 (비동기)
            cmd = [
                str(soffice_path),
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', str(temp_dir),
                str(input_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"LibreOffice 변환 실패: {stderr.decode()}")
                raise HTTPException(
                    status_code=500,
                    detail="PDF 변환에 실패했습니다"
                )
            
            # 변환된 파일을 CONVERTED_DIR로 이동
            temp_pdf = Path(temp_dir) / pdf_filename
            if temp_pdf.exists():
                # 비동기 파일 이동
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, temp_pdf.rename, pdf_path)
                logger.info(f"PDF 변환 완료: {pdf_path}")
                return pdf_path
            else:
                raise HTTPException(
                    status_code=500,
                    detail="변환된 PDF 파일을 찾을 수 없습니다"
                )
                
        except Exception as e:
            logger.error(f"PDF 변환 중 오류: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"PDF 변환 실패: {str(e)}"
            )


async def download_and_cache_file(redis_client: redis.Redis, url: str, settings: Config) -> Tuple[Path, str, bool]:
    """
    URL로 키를 만들어서 캐쉬에 있는지 체크 있으면 캐쉬를 없으면 URL에서 파일을 다운로드하고 캐시에 저장
    Returns: (파일 경로, 원본 파일명, cache_hit)
    """
    from app.core.utils import generate_cache_key, validate_file_extension  # 순환 import 방지
    
    # URL에서 파일명 추출
    try:
        parsed_url = url.split('/')[-1].split('?')[0]  # 간단한 파일명 추출
        if not parsed_url:
            parsed_url = "downloaded_file"
    except:
        parsed_url = "downloaded_file"
    
    # 캐시 키 생성
    cache_key = generate_cache_key(url)
    
    # Redis에서 캐시된 파일 확인
    cached_filename = redis_client.get(cache_key)
    if cached_filename:
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
        logger.error(f"HTTP 클라이언트 오류: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"파일 다운로드 중 네트워크 오류: {str(e)}"
        )
    except Exception as e:
        logger.error(f"파일 다운로드 중 예상치 못한 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"파일 다운로드 중 오류: {str(e)}"
        )


async def copy_and_cache_file(path: str, redis_client: redis.Redis, settings: Config) -> Tuple[Path, str, bool]:
    """
    로컬 파일을 캐시에 복사, 이미 캐쉬에 있으면 재사용
    Returns: (파일 경로, 원본 파일명, cache_hit)
    """
    from app.core.utils import generate_cache_key, validate_file_extension, AIOFILES_AVAILABLE  # 순환 import 방지
    
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


async def url_download_and_convert(request, url: str, output_format: str) -> str:
    """
    URL에서 파일을 다운로드하고 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    import time
    from app.core.view_lib import convert_to_html  # 순환 import 방지
    
    redis_client = request.app.state.redis
    stats_manager = request.app.state.stats_db
    start_time = time.time()

    converted_dir = Path(settings.CONVERTED_DIR)
    if output_format.lower().endswith('pdf'):
        file_path, original_filename, cache_hit = await download_and_cache_file(redis_client, url, settings)
        output_path = await convert_to_pdf(file_path, converted_dir)

    elif output_format.lower().endswith('html'):
        file_path, original_filename, cache_hit = await download_and_cache_file(redis_client, url, settings)
        output_path = await convert_to_html(file_path, converted_dir, original_filename)
    
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


async def local_file_copy_and_convert(request, path: str, output_format: str) -> str:
    """
    로컬 파일을 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    import time
    from app.core.view_lib import convert_to_html  # 순환 import 방지
    
    redis_client = request.app.state.redis
    stats_manager = request.app.state.stats_db
    start_time = time.time()

    converted_dir = Path(settings.CONVERTED_DIR)
    if output_format.lower().endswith('pdf'):
        file_path, original_filename, cache_hit = await copy_and_cache_file(path, redis_client, settings)
        output_path = await convert_to_pdf(file_path, converted_dir)

    elif output_format.lower().endswith('html'):
        file_path, original_filename, cache_hit = await copy_and_cache_file(path, redis_client, settings)
        output_path = await convert_to_html(file_path, converted_dir, original_filename)

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