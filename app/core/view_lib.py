"""
View Library  
문서 뷰어 관련 기능들을 모아놓은 라이브러리
다양한 파일 형식을 HTML로 변환하는 기능들
"""

import csv
from io import StringIO
from pathlib import Path
import time
from typing import Tuple

import redis
from fastapi import HTTPException, Request
from jinja2 import Environment, FileSystemLoader

from app.core.config import Config, settings
from app.core.logger import get_logger
from app.core.utils import copy_and_cache_file, download_and_cache_file
from doc.utils import convert_to_html

logger = get_logger(__name__)


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


def view_pdf_to_html(pdf_path: Path, html_path: Path, original_filename: str = None) -> Path:
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
        return view_basic_pdf_to_html(pdf_path, html_path, original_filename)


def view_basic_pdf_to_html(pdf_path: Path, html_path: Path, original_filename: str = None) -> Path:
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


def view_csv_to_html(csv_path: Path, html_path: Path, original_filename: str = None) -> Path:
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


def view_txt_to_html(txt_path: Path, html_path: Path, original_filename: str = None) -> Path:
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


def view_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
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
        return view_basic_image_to_html(image_path, html_path, original_filename)


def view_basic_image_to_html(image_path: Path, html_path: Path, original_filename: str = None) -> Path:
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


def view_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
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
        return view_basic_md_to_html(md_path, html_path, original_filename)
    except Exception as e:
        logger.error(f"마크다운 HTML 변환 실패: {str(e)}")
        return view_basic_md_to_html(md_path, html_path, original_filename)


def view_basic_md_to_html(md_path: Path, html_path: Path, original_filename: str = None) -> Path:
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


# async def view_to_html(input_path: Path, CONVERTED_DIR: Path, original_filename: str = None) -> Path:
#     """
#     LibreOffice를 사용해 파일을 HTML로 변환 (비동기)
#     특정 파일 타입은 전용 변환 함수 사용 (한글 인코딩 문제 해결)
#     Returns: 변환된 HTML 파일 경로
#     """
#     import asyncio
    
#     # 이미 HTML인 경우 그대로 반환
#     if input_path.suffix.lower() in {'.html', '.htm'}:
#         return input_path
    
#     # 변환된 파일 경로
#     html_filename = f"{input_path.stem}.html"
#     html_path = CONVERTED_DIR / html_filename
    
#     # 이미 변환된 파일이 있으면 반환
#     if html_path.exists():
#         return html_path
    
#     # 파일 타입별 전용 변환 함수 사용 (이들은 동기이므로 executor 사용)
#     if input_path.suffix.lower() == '.csv':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, view_csv_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.txt':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, view_txt_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}:
#         return await asyncio.get_event_loop().run_in_executor(
#             None, view_image_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.md':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, view_md_to_html, input_path, html_path, original_filename
#         )
#     elif input_path.suffix.lower() == '.pdf':
#         return await asyncio.get_event_loop().run_in_executor(
#             None, view_pdf_to_html, input_path, html_path, original_filename
#         )
#     else:
#         raise RuntimeError("지원하지 않는 파일 형식입니다")


async def local_file_copy_and_view(request: Request, path: str, output_format: str) -> str:
    """
    로컬 파일을 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """

    stats_manager = request.app.state.stats_db
    start_time = time.time()

    file_path, original_filename, cache_hit = await copy_and_cache_file(request, path, settings)
    output_path = await convert_to_html(request, file_path, original_filename)

    logger.info(f"path :{path} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/html/{output_path.name}"
    # url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/{output_format.lower()}/{output_path.name}"
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

async def url_download_and_view(request: Request, url: str, output_format: str) -> str:
    """
    URL에서 파일을 다운로드하고 지정된 형식으로 변환 (비동기)
    Returns: 변환된 파일의 URL (임시로 생성된 URL)
    """
    stats_manager = request.app.state.stats_db
    start_time = time.time()

    file_path, original_filename, cache_hit = await download_and_cache_file(request, url, settings)
    output_path = await convert_to_html(request, file_path, original_filename)
    
    logger.info(f"url :{url} 에서 다운로드, 원래파일명:{original_filename},  변환된 파일 {output_path}로 저장")
    # url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/{output_format.lower()}/{output_path.name}"
    url = f"{settings.PROTOCOL}://{settings.HOST}:{settings.PORT}/aview/html/{output_path.name}"
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

