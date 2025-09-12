"""
파일 확장자 정의 및 분류
A-View에서 지원하는 파일 형식들의 확장자를 체계적으로 정의
"""

# 기본 파일 타입별 확장자 정의
TEXT_BASE_EXTENSION = {
    '.txt', '.md'
}

IMAGE_BASE_EXTENSION = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'
}

OFFICE_BASE_EXTENSION = {
    '.doc', '.docx', '.odt', '.rtf',        # 문서
    '.xls', '.xlsx', '.ods',                # 스프레드시트
    '.ppt', '.pptx', '.odp'                 # 프레젠테이션
}

DOCUMENT_BASE_EXTENSION = {
    '.pdf',                                 # PDF (이미 변환된 파일)
    '.csv'                                  # CSV (특별 처리)
}

# 용도별 확장자 집합 조합
CONVERTABLE_EXTENSION = OFFICE_BASE_EXTENSION.copy()
"""LibreOffice로 PDF/HTML 변환이 가능한 확장자"""

VIEWABLE_EXTENSION = (
    TEXT_BASE_EXTENSION | 
    IMAGE_BASE_EXTENSION | 
    OFFICE_BASE_EXTENSION | 
    DOCUMENT_BASE_EXTENSION
)
"""View API에서 처리 가능한 모든 확장자"""

# 하위 호환성을 위한 alias
SUPPORTED_EXTENSIONS = VIEWABLE_EXTENSION
"""기존 코드 호환성을 위한 별칭"""

# 확장자별 처리 방식 매핑 (향후 FILE_TYPE_CONFIG 전환용)
EXTENSION_HANDLER_MAP = {
    # 텍스트 파일
    '.txt': 'view_txt_to_html',
    '.md': 'view_md_to_html',
    
    # 이미지 파일
    '.png': 'view_image_to_html',
    '.jpg': 'view_image_to_html',
    '.jpeg': 'view_image_to_html',
    '.gif': 'view_image_to_html',
    '.bmp': 'view_image_to_html',
    '.tiff': 'view_image_to_html',
    '.webp': 'view_image_to_html',
    
    # CSV 파일 (특별 처리)
    '.csv': 'view_csv_to_html',
    
    # 오피스 파일들 (LibreOffice 처리)
    '.doc': 'convert_with_libreoffice',
    '.docx': 'convert_with_libreoffice',
    '.odt': 'convert_with_libreoffice',
    '.rtf': 'convert_with_libreoffice',
    '.xls': 'convert_with_libreoffice',
    '.xlsx': 'convert_with_libreoffice',
    '.ods': 'convert_with_libreoffice',
    '.ppt': 'convert_with_libreoffice',
    '.pptx': 'convert_with_libreoffice',
    '.odp': 'convert_with_libreoffice',
    
    # PDF (그대로 반환)
    '.pdf': None  # 변환 불필요
}

# 파일 타입 분류 함수들
def get_file_type(extension: str) -> str:
    """파일 확장자로부터 파일 타입 반환"""
    ext = extension.lower()
    if ext in TEXT_BASE_EXTENSION:
        return 'text'
    elif ext in IMAGE_BASE_EXTENSION:
        return 'image'
    elif ext in OFFICE_BASE_EXTENSION:
        return 'office'
    elif ext in DOCUMENT_BASE_EXTENSION:
        return 'document'
    else:
        return 'unknown'

def is_convertable(extension: str) -> bool:
    """LibreOffice로 변환 가능한 파일인지 확인"""
    return extension.lower() in CONVERTABLE_EXTENSION

def is_viewable(extension: str) -> bool:
    """View API에서 처리 가능한 파일인지 확인"""
    return extension.lower() in VIEWABLE_EXTENSION

def get_handler_function_name(extension: str) -> str:
    """확장자에 맞는 처리 함수명 반환"""
    return EXTENSION_HANDLER_MAP.get(extension.lower(), 'convert_with_libreoffice')

# 디버깅/정보 제공용 함수들
def get_all_supported_extensions() -> set:
    """지원하는 모든 확장자 반환"""
    return VIEWABLE_EXTENSION

def get_extensions_by_type(file_type: str) -> set:
    """파일 타입별 확장자 목록 반환"""
    type_map = {
        'text': TEXT_BASE_EXTENSION,
        'image': IMAGE_BASE_EXTENSION,
        'office': OFFICE_BASE_EXTENSION,
        'document': DOCUMENT_BASE_EXTENSION
    }
    return type_map.get(file_type, set())

def print_extension_summary():
    """확장자 정의 현황 출력 (디버깅용)"""
    print("=== A-View 지원 파일 확장자 현황 ===")
    print(f"텍스트 파일: {sorted(TEXT_BASE_EXTENSION)}")
    print(f"이미지 파일: {sorted(IMAGE_BASE_EXTENSION)}")
    print(f"오피스 파일: {sorted(OFFICE_BASE_EXTENSION)}")
    print(f"문서 파일: {sorted(DOCUMENT_BASE_EXTENSION)}")
    print(f"변환 가능: {sorted(CONVERTABLE_EXTENSION)}")
    print(f"뷰어 지원: {sorted(VIEWABLE_EXTENSION)}")
    print(f"총 지원 확장자 수: {len(VIEWABLE_EXTENSION)}개")

if __name__ == "__main__":
    # 테스트용 코드
    print_extension_summary()
    
    # 예제 테스트
    test_files = ['.docx', '.png', '.txt', '.csv', '.pdf', '.xyz']
    for ext in test_files:
        print(f"{ext}: 타입={get_file_type(ext)}, 변환가능={is_convertable(ext)}, "
              f"뷰어지원={is_viewable(ext)}, 핸들러={get_handler_function_name(ext)}")
