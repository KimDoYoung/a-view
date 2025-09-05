from fastapi import Query
from pydantic import BaseModel, field_validator, model_validator
from enum import Enum
from typing import Optional, Self
from pathlib import Path
import os

from app.utils import CONVERTABLE_EXTENSIONS

class OutputFormat(str, Enum):
    """지원하는 출력 형식"""
    PDF = "pdf"
    HTML = "html"
    # 추후 LibreOffice 지원 형식 추가 예정
    # DOCX = "docx"
    # TXT = "txt"
    # ODT = "odt"

# View용 파일 확장자별 출력 포맷 매핑
VIEW_FORMAT_MAPPING = {
    # 오피스 파일들 -> PDF
    '.xlsx': OutputFormat.PDF,
    '.xls': OutputFormat.PDF,
    '.docx': OutputFormat.PDF,
    '.doc': OutputFormat.PDF,
    '.pptx': OutputFormat.PDF,
    '.ppt': OutputFormat.PDF,
    
    # 텍스트 기반 파일들 -> HTML
    '.txt': OutputFormat.HTML,
    '.csv': OutputFormat.HTML,
    '.md': OutputFormat.HTML,
    
    # 이미지 파일들 -> HTML (이미지를 HTML로 감싸서 표시)
    '.jpg': OutputFormat.HTML,
    '.jpeg': OutputFormat.HTML,
    '.png': OutputFormat.HTML,
    '.gif': OutputFormat.HTML,
    '.bmp': OutputFormat.HTML
}

class ConvertParams(BaseModel):
    """변환 요청 파라미터 모델 (Schema)"""
    url: Optional[str] = None
    path: Optional[str] = None
    output: OutputFormat = OutputFormat.HTML
    
    @model_validator(mode='after')
    def validate_source(cls, values):
        """url과 path 중 하나만 제공되어야 함"""
        url = values.url
        path = values.path
        
        if not url and not path:
            raise ValueError('url 또는 path 중 하나는 반드시 제공되어야 합니다')
        
        if url and path:
            raise ValueError('url과 path는 동시에 제공할 수 없습니다')
        
        # 파일 경로가 있는 경우, 입력 파일과 출력 파일 형식이 동일한지 체크
        if path:
            path_obj = Path(path)
            if path_obj.suffix.lower() == f'.{values.output.value}':
                raise ValueError(f'입력 파일과 출력 파일 형식이 동일합니다: {path_obj.suffix}')
        
        return values
    
    @field_validator('url')
    def validate_url(cls, v):
        """URL 형식 검증"""
        if v is None:
            return v
        
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')
        
        # 지원하는 파일 확장자 체크 (선택사항)
        supported_extensions = CONVERTABLE_EXTENSIONS
        url_lower = v.lower()
        if '.' in Path(v).suffix:
            if not any(url_lower.endswith(ext) for ext in supported_extensions):
                raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        return v
    
    @field_validator('path')
    def validate_path(cls, v):
        """파일 경로 검증"""
        if v is None:
            return v
        
        # Windows/Linux 경로 형식 둘 다 지원
        path_obj = Path(v)
        
        # 파일 존재 여부 체크
        if not path_obj.exists():
            raise ValueError(f'파일이 존재하지 않습니다: {v}')
        
        if not path_obj.is_file():
            raise ValueError(f'디렉토리가 아닌 파일이어야 합니다: {v}')
            
        # 지원하는 파일 확장자 체크
        supported_extensions = CONVERTABLE_EXTENSIONS
        if path_obj.suffix.lower() not in supported_extensions:
            raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        
        # 파일 읽기 권한 체크
        if not os.access(v, os.R_OK):
            raise ValueError(f'파일 읽기 권한이 없습니다: {v}')
        
        return v
    
    @property
    def is_url_source(self) -> bool:
        """URL 소스인지 확인"""
        return self.url is not None
    
    @property
    def is_path_source(self) -> bool:
        """경로 소스인지 확인"""
        return self.path is not None
    
    @property
    def source_value(self) -> str:
        """소스 값 반환 (url 또는 path)"""
        return self.url if self.url else self.path

# FastAPI에서 쿼리 파라미터로 받기 위한 의존성 함수
def get_convert_params(
    url: Optional[str] = Query(None, description="변환할 문서의 URL"),
    path: Optional[str] = Query(None, description="변환할 문서의 로컬 경로"),
    output: OutputFormat = Query(OutputFormat.HTML, description="출력 형식 (pdf 또는 html)")
) -> ConvertParams:
    """쿼리 파라미터를 Pydantic 모델로 변환"""
    return ConvertParams(url=url, path=path, output=output)

# POST 요청용 모델 (선택사항)
class ConvertRequest(BaseModel):
    """POST 요청용 변환 모델"""
    url: Optional[str] = None
    path: Optional[str] = None
    output: OutputFormat = OutputFormat.HTML
    
    # ConvertParams와 동일한 검증 로직 적용
    @model_validator(mode='after')
    def validate_source(self) -> Self:
        if not self.url and not self.path:
            raise ValueError('url 또는 path 중 하나는 반드시 제공되어야 합니다')
        
        if self.url and self.path:
            raise ValueError('url과 path는 동시에 제공할 수 없습니다')
        
        return self
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if v is None:
            return v
        
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')

        supported_extensions = CONVERTABLE_EXTENSIONS
        url_lower = v.lower()
        
        if '.' in Path(v).suffix:
            if not any(url_lower.endswith(ext) for ext in supported_extensions):
                raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        
        return v
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v):
        if v is None:
            return v
        
        path_obj = Path(v)
        
        if not path_obj.exists():
            raise ValueError(f'파일이 존재하지 않습니다: {v}')
        
        if not path_obj.is_file():
            raise ValueError(f'디렉토리가 아닌 파일이어야 합니다: {v}')

        supported_extensions = CONVERTABLE_EXTENSIONS
        if path_obj.suffix.lower() not in supported_extensions:
            raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        
        if not os.access(v, os.R_OK):
            raise ValueError(f'파일 읽기 권한이 없습니다: {v}')
        
        return v

class ConvertResponse(BaseModel):
    """변환 응답 모델 - 심플하게"""
    success: bool
    url: str = ""
    message: str
    
    @classmethod
    def success_response(cls, url: str, message: str = "변환됨") -> "ConvertResponse":
        """성공 응답 생성"""
        return cls(success=True, url=url, message=message)
    
    @classmethod
    def error_response(cls, message: str) -> "ConvertResponse":
        """실패 응답 생성"""
        return cls(success=False, url="", message=message)


class ViewParams(BaseModel):
    """뷰 요청 파라미터 모델 (Schema)"""
    url: Optional[str] = None
    path: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_source(self):
        """url과 path 중 하나만 제공되어야 함"""
        url = self.url
        path = self.path
        
        if not url and not path:
            raise ValueError('url 또는 path 중 하나는 반드시 제공되어야 합니다')
        
        if url and path:
            raise ValueError('url과 path는 동시에 제공할 수 없습니다')
        
        return self
    
    @field_validator('url')
    def validate_url(cls, v):
        """URL 형식 검증"""
        if v is None:
            return v
        
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL은 http:// 또는 https://로 시작해야 합니다')
        
        # View에서 지원하는 파일 확장자 체크
        supported_extensions = list(VIEW_FORMAT_MAPPING.keys())
        url_lower = v.lower()
        if '.' in Path(v).suffix:
            if not any(url_lower.endswith(ext) for ext in supported_extensions):
                raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        return v
    
    @field_validator('path')
    def validate_path(cls, v):
        """파일 경로 검증"""
        if v is None:
            return v
        
        # Windows/Linux 경로 형식 둘 다 지원
        path_obj = Path(v)
        
        # 파일 존재 여부 체크
        if not path_obj.exists():
            raise ValueError(f'파일이 존재하지 않습니다: {v}')
        
        if not path_obj.is_file():
            raise ValueError(f'디렉토리가 아닌 파일이어야 합니다: {v}')
            
        # View에서 지원하는 파일 확장자 체크
        supported_extensions = list(VIEW_FORMAT_MAPPING.keys())
        if path_obj.suffix.lower() not in supported_extensions:
            raise ValueError(f'지원하지 않는 파일 형식입니다. 지원 형식: {supported_extensions}')
        
        # 파일 읽기 권한 체크
        if not os.access(v, os.R_OK):
            raise ValueError(f'파일 읽기 권한이 없습니다: {v}')
        
        return v
    
    @property
    def is_url_source(self) -> bool:
        """URL 소스인지 확인"""
        return self.url is not None
    
    @property
    def is_path_source(self) -> bool:
        """경로 소스인지 확인"""
        return self.path is not None
    
    @property
    def source_value(self) -> str:
        """소스 값 반환 (url 또는 path)"""
        return self.url if self.url else self.path
    
    @property
    def auto_output_format(self) -> OutputFormat:
        """파일 확장자에 따른 자동 출력 포맷 결정"""
        source = self.source_value
        file_ext = Path(source).suffix.lower()
        
        # VIEW_FORMAT_MAPPING에서 확장자에 해당하는 포맷 반환
        return VIEW_FORMAT_MAPPING.get(file_ext, OutputFormat.HTML)
    
    @property
    def is_pdf_output(self) -> bool:
        """PDF 출력인지 확인"""
        return self.auto_output_format == OutputFormat.PDF
    
    @property
    def is_html_output(self) -> bool:
        """HTML 출력인지 확인"""
        return self.auto_output_format == OutputFormat.HTML


# FastAPI에서 쿼리 파라미터로 받기 위한 의존성 함수
def get_view_params(
    url: Optional[str] = Query(None, description="보기할 문서의 URL"),
    path: Optional[str] = Query(None, description="보기할 문서의 로컬 경로")
) -> ViewParams:
    """쿼리 파라미터를 ViewParams 모델로 변환"""
    return ViewParams(url=url, path=path)