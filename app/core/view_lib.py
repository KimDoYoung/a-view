"""
View Library  
문서 뷰어 관련 기능들을 모아놓은 라이브러리
다양한 파일 형식을 HTML로 변환하는 기능들
"""

import csv
import os
import subprocess
from io import StringIO
from pathlib import Path
from typing import Tuple

import redis
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader

from app.core.config import Config
from app.core.logger import logger


async def get_cached_pdf(redis_client: redis.Redis, url: str, settings: Config) -> Tuple[Path, str]:
    """
    URL에서 PDF 파일을 가져와서 캐시에 저장
    Returns: (PDF_파일_경로, 원본_파일명)
    """
    from app.core.convert_lib import download_and_cache_file, convert_to_pdf  # 순환 import 방지
    
    # 파일 다운로드 또는 캐시에서 가져오기
    cached_path, original_filename, cache_hit = await download_and_cache_file(
        redis_client, url, settings
    )
    
    # PDF로 변환
    pdf_path = await convert_to_pdf(cached_path, Path(settings.CONVERTED_DIR))
    
    return pdf_path, original_filename


def convert_pdf_to_html(pdf_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    PDF 파일을 HTML로 감싸서 브라우저에서 볼 수 있도록 함
    브라우저의 내장 PDF 뷰어를 사용
    Returns: 변환된 HTML 파일 경로
    """
    try:
        # PDF 파일 정보 추출
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        # PDF 파일의 웹 서버 URL 생성 (정적 파일 서빙용)
        pdf_filename = pdf_path.name
        pdf_url = f"/pdf/{pdf_filename}"  # aview_routes.py의 /pdf/{filename} 엔드포인트 사용
        
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
        current_dir = Path(__file__).parent.parent  # app 디렉토리
        template_dir = current_dir / "templates"
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
        # 기본 파일 정보
        file_size = pdf_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        pdf_filename = pdf_path.name
        
        # PDF 파일의 웹 서버 URL 생성
        pdf_url = f"/pdf/{pdf_filename}"
        
        # Jinja2 템플릿 로드
        current_dir = Path(__file__).parent.parent  # app 디렉토리
        template_dir = current_dir / "templates"
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
    CSV 파일을 HTML 테이블로 변환
    """
    try:
        # CSV 파일 읽기
        csv_data = []
        headers = []
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            # CSV 내용을 먼저 읽어서 인코딩 문제 체크
            content = f.read()
            
        # UTF-8로 읽기 시도, 실패시 cp949로 재시도
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        csv_content = None
        
        for encoding in encodings:
            try:
                with open(csv_path, 'r', encoding=encoding, errors='replace') as f:
                    csv_content = f.read()
                    logger.info(f"CSV 파일 인코딩: {encoding}")
                    break
            except UnicodeDecodeError:
                continue
        
        if csv_content is None:
            raise Exception("CSV 파일 인코딩을 확인할 수 없습니다")
        
        # CSV 파싱
        csv_reader = csv.reader(StringIO(csv_content))
        rows = list(csv_reader)
        
        if not rows:
            raise Exception("CSV 파일이 비어있습니다")
        
        # 첫 번째 행을 헤더로 사용
        headers = rows[0]
        csv_data = rows[1:] if len(rows) > 1 else []
        
        # 파일 정보
        file_size = csv_path.stat().st_size
        row_count = len(csv_data)
        col_count = len(headers)
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        # 템플릿 로드
        template = env.get_template('viewer/csv.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else csv_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            headers=headers,
            csv_data=csv_data,
            file_size=file_size,
            row_count=row_count,
            col_count=col_count
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"CSV를 HTML로 변환 완료: {csv_path} -> {html_path} ({row_count}행)")
        return html_path
        
    except Exception as e:
        logger.error(f"CSV HTML 변환 실패: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"CSV 변환 중 오류 발생: {str(e)}"
        )


def convert_txt_to_html(txt_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    텍스트 파일을 HTML로 변환
    """
    try:
        # 텍스트 파일 읽기 (여러 인코딩 시도)
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        txt_content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(txt_path, 'r', encoding=encoding, errors='replace') as f:
                    txt_content = f.read()
                    used_encoding = encoding
                    logger.info(f"텍스트 파일 인코딩: {encoding}")
                    break
            except UnicodeDecodeError:
                continue
        
        if txt_content is None:
            raise Exception("텍스트 파일 인코딩을 확인할 수 없습니다")
        
        # 파일 정보
        file_size = txt_path.stat().st_size
        line_count = len(txt_content.splitlines())
        char_count = len(txt_content)
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        # 템플릿 로드
        template = env.get_template('viewer/text.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else txt_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            content=txt_content,
            file_size=file_size,
            line_count=line_count,
            char_count=char_count,
            encoding=used_encoding
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"텍스트를 HTML로 변환 완료: {txt_path} -> {html_path} ({line_count}행)")
        return html_path
        
    except Exception as e:
        logger.error(f"텍스트 HTML 변환 실패: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"텍스트 변환 중 오류 발생: {str(e)}"
        )


def convert_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    이미지 파일을 HTML로 변환 (EXIF 정보 포함)
    """
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        # 이미지 열기
        with Image.open(image_path) as img:
            # 기본 이미지 정보
            width, height = img.size
            format = img.format
            mode = img.mode
            
            # EXIF 데이터 추출
            exif_data = {}
            if hasattr(img, '_getexif'):
                exif = img._getexif()
                if exif is not None:
                    for tag, value in exif.items():
                        tag_name = TAGS.get(tag, tag)
                        exif_data[tag_name] = str(value)
        
        # 파일 정보
        file_size = image_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        # 이미지 URL 생성 (정적 파일 서빙용)
        image_filename = image_path.name
        image_url = f"/static/cache/{image_filename}"
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        # 숫자 포매팅 필터
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        # 템플릿 로드
        template = env.get_template('viewer/image.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else image_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            image_url=image_url,
            width=width,
            height=height,
            format=format,
            mode=mode,
            file_size=file_size,
            file_size_mb=round(file_size_mb, 2),
            exif_data=exif_data
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"이미지를 HTML로 변환 완료: {image_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"이미지 HTML 변환 실패: {str(e)}")
        # 실패 시 기본 구현 사용
        return convert_basic_image_to_html(image_path, html_path, original_filename)


def convert_basic_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    기본 이미지 HTML 변환 (EXIF 없이)
    """
    try:
        # 파일 정보
        file_size = image_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        # 이미지 URL 생성
        image_filename = image_path.name
        image_url = f"/static/cache/{image_filename}"
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/image.html')
        
        # 템플릿 렌더링 (기본값들)
        display_filename = original_filename if original_filename else image_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            image_url=image_url,
            width='Unknown',
            height='Unknown',
            format='Unknown',
            mode='Unknown',
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
        raise HTTPException(
            status_code=500,
            detail=f"이미지 변환 중 오류 발생: {str(e)}"
        )


def convert_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    마크다운 파일을 HTML로 변환
    """
    try:
        import markdown
        
        # 마크다운 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        md_content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(md_path, 'r', encoding=encoding, errors='replace') as f:
                    md_content = f.read()
                    used_encoding = encoding
                    logger.info(f"마크다운 파일 인코딩: {encoding}")
                    break
            except UnicodeDecodeError:
                continue
        
        if md_content is None:
            raise Exception("마크다운 파일 인코딩을 확인할 수 없습니다")
        
        # 마크다운을 HTML로 변환 (확장 기능 포함)
        md_processor = markdown.Markdown(extensions=[
            'tables',      # 테이블 지원
            'fenced_code', # 코드 블록 지원  
            'codehilite',  # 코드 하이라이팅
            'toc',         # 목차 생성
            'nl2br'        # 줄바꿈을 <br>로 변환
        ])
        
        html_body = md_processor.convert(md_content)
        toc = getattr(md_processor, 'toc', '')
        
        # 파일 정보
        file_size = md_path.stat().st_size
        line_count = len(md_content.splitlines())
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/markdown.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else md_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            content=html_body,
            toc=toc,
            file_size=file_size,
            line_count=line_count,
            encoding=used_encoding
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"마크다운을 HTML로 변환 완료: {md_path} -> {html_path}")
        return html_path
        
    except ImportError:
        logger.warning("markdown 라이브러리가 설치되지 않아 기본 구현을 사용합니다")
        return convert_basic_md_to_html(md_path, html_path, original_filename)
    except Exception as e:
        logger.error(f"마크다운 HTML 변환 실패: {str(e)}")
        return convert_basic_md_to_html(md_path, html_path, original_filename)


def convert_basic_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
    """
    기본 마크다운 HTML 변환 (markdown 라이브러리 없이)
    """
    try:
        # 마크다운 파일 읽기
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        md_content = None
        used_encoding = None
        
        for encoding in encodings:
            try:
                with open(md_path, 'r', encoding=encoding, errors='replace') as f:
                    md_content = f.read()
                    used_encoding = encoding
                    logger.info(f"마크다운 파일 인코딩: {encoding}")
                    break
            except UnicodeDecodeError:
                continue
        
        if md_content is None:
            raise Exception("마크다운 파일 인코딩을 확인할 수 없습니다")
        
        # 간단한 마크다운 변환 (제한적)
        html_body = md_content
        html_body = html_body.replace('&', '&amp;')
        html_body = html_body.replace('<', '&lt;')
        html_body = html_body.replace('>', '&gt;')
        html_body = html_body.replace('\n', '<br>\n')
        
        # 파일 정보
        file_size = md_path.stat().st_size
        line_count = len(md_content.splitlines())
        
        # Jinja2 템플릿 환경 설정
        current_dir = Path(__file__).parent.parent
        template_dir = current_dir / "templates"
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        
        def number_format(value):
            return f"{value:,}"
        env.filters['number_format'] = number_format
        
        template = env.get_template('viewer/markdown.html')
        
        # 템플릿 렌더링
        display_filename = original_filename if original_filename else md_path.name
        html_content = template.render(
            filename=display_filename,
            original_filename=display_filename,
            content=html_body,
            toc='',
            file_size=file_size,
            line_count=line_count,
            encoding=used_encoding
        )
        
        # HTML 파일로 저장
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"마크다운을 기본 HTML로 변환 완료: {md_path} -> {html_path}")
        return html_path
        
    except Exception as e:
        logger.error(f"기본 마크다운 HTML 변환 실패: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"마크다운 변환 중 오류 발생: {str(e)}"
        )


def convert_with_libreoffice(input_path: Path, html_path: Path) -> Path:
    """
    LibreOffice를 사용하여 문서를 HTML로 변환
    """
    from .utils import find_soffice  # 순환 import 방지
    
    try:
        # LibreOffice 실행 파일 찾기
        libre_office = find_soffice()
        if not libre_office:
            raise HTTPException(
                status_code=500,
                detail="LibreOffice 실행 파일을 찾을 수 없습니다"
            )
        
        # 출력 디렉토리 생성
        output_dir = html_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # LibreOffice 임시 프로필 디렉토리
        LO_PROFILE_DIR = Path("/tmp/lo_profile")
        LO_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        lo_profile = LO_PROFILE_DIR.resolve()
        
        # LibreOffice HTML 변환 명령
        cmd = [
            str(libre_office),
            "--headless", "--nologo", "--norestore", "--nolockcheck", "--nodefault", "--nocrashreport",
            f"-env:UserInstallation=file:///{lo_profile.as_posix()}",
            "--convert-to", "html",
            "--outdir", str(output_dir),
            str(input_path)
        ]
        
        logger.info(f"LibreOffice HTML 변환 명령: {' '.join(cmd)}")
        
        # subprocess로 LibreOffice 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,  # 60초 타임아웃
            cwd=str(input_path.parent)
        )
        
        logger.info(f"LibreOffice 종료 코드: {result.returncode}")
        if result.stdout:
            logger.info(f"LibreOffice stdout: {result.stdout}")
        if result.stderr:
            logger.warning(f"LibreOffice stderr: {result.stderr}")
        
        if result.returncode != 0:
            error_msg = f"LibreOffice HTML 변환 실패 (코드: {result.returncode})"
            if result.stderr:
                error_msg += f" - {result.stderr}"
            raise HTTPException(status_code=500, detail=error_msg)
        
        # 생성된 HTML 파일 확인
        expected_html = output_dir / f"{input_path.stem}.html"
        
        if not expected_html.exists():
            # 생성된 HTML 파일들 확인
            generated_files = list(output_dir.glob("*.html"))
            logger.info(f"생성된 HTML 파일들: {generated_files}")
            
            if generated_files:
                # 가장 최근에 생성된 파일 사용
                expected_html = max(generated_files, key=os.path.getctime)
                logger.info(f"생성된 HTML 파일 사용: {expected_html}")
            else:
                raise HTTPException(
                    status_code=500,
                    detail="HTML 파일 변환에 성공했으나 파일을 찾을 수 없습니다"
                )
        
        # 원하는 경로로 파일 이동 (필요시)
        if expected_html != html_path:
            expected_html.rename(html_path)
        
        logger.info(f"LibreOffice HTML 변환 완료: {input_path} -> {html_path}")
        return html_path
        
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice HTML 변환 시간 초과")
        raise HTTPException(
            status_code=500,
            detail="파일 변환 시간이 초과되었습니다"
        )
    except Exception as e:
        logger.error(f"LibreOffice HTML 변환 중 예상치 못한 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"HTML 변환 중 오류 발생: {str(e)}"
        )


async def convert_with_libreoffice_async(input_path: Path, html_path: Path) -> Path:
    """
    LibreOffice를 사용한 비동기 변환
    """
    import asyncio
    CONVERTED_DIR = html_path.parent
    
    # LibreOffice 실행 파일 찾기
    from .utils import find_soffice  # 순환 import 방지
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
        "--convert-to", "html",
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


async def convert_to_html(input_path: Path, CONVERTED_DIR: Path, original_filename: str = None) -> Path:
    """
    LibreOffice를 사용해 파일을 HTML로 변환 (비동기)
    특정 파일 타입은 전용 변환 함수 사용 (한글 인코딩 문제 해결)
    Returns: 변환된 HTML 파일 경로
    """
    import asyncio
    
    # 이미 HTML인 경우 그대로 반환
    if input_path.suffix.lower() in {'.html', '.htm'}:
        return input_path
    
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
    # 그 외 파일들은 LibreOffice 사용 (비동기)
    return await convert_with_libreoffice_async(input_path, html_path)