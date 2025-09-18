"""
A-View 설정 클래스
기존 방식을 사용한 간단한 설정 관리
"""

import os

from dotenv import load_dotenv


class Config:
    def __init__(self):
        # 환경 구분
        self.PROFILE_NAME = os.getenv('AVIEW_MODE', 'local')
        load_dotenv(dotenv_path=f'.env.{self.PROFILE_NAME}')
        
        # 애플리케이션 기본 설정
        self.APP_NAME = os.getenv('APP_NAME', 'A-View Document Viewer')
        self.VERSION = os.getenv('VERSION', '1.0.0')
        self.DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
        
        # 서버 설정
        self.PROTOCOL = os.getenv('PROTOCOL', 'http')
        self.HOST = os.getenv('HOST', '0.0.0.0')
        self.PORT = int(os.getenv('PORT', '8003'))
        self.RELOAD = os.getenv('RELOAD', 'true').lower() == 'true'
        
        # SSL 설정
        self.SSL_CERT_FILE = os.getenv('SSL_CERT_FILE', None)
        self.SSL_KEY_FILE = os.getenv('SSL_KEY_FILE', None)
        self.SSL_KEY_PASSWORD = os.getenv('SSL_KEY_PASSWORD', None)  # 필요 시
        self.SSL_CA_FILE = os.getenv('SSL_CA_FILE', None)           

        # Redis 설정
        self.REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
        self.REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
        self.REDIS_DB = int(os.getenv('REDIS_DB', '0'))
        self.REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
        
        # 캐시 설정
        self.BASE_DIR = os.getenv('BASE_DIR', 'C:/tmp/aview' if os.name == 'nt' else '/aview/data')
        self.CACHE_DIR = os.getenv('CACHE_DIR', f'{self.BASE_DIR}/cache')
        self.CONVERTED_DIR = f'{self.CACHE_DIR}/converted'
        self.CACHE_TTL = int(os.getenv('CACHE_TTL', '86400'))  # 24시간
        # 통계 DB
        self.STATS_DB_PATH = os.getenv('STATS_DB_PATH', f'{self.BASE_DIR}/db/aview_stats.db') 
        
        # 템플릿 디렉토리 설정
        from pathlib import Path
        self.TEMPLATE_DIR = Path(__file__).parent.parent / "templates" 
        
        # LibreOffice 설정
        self.LIBREOFFICE_TIMEOUT = int(os.getenv('LIBREOFFICE_TIMEOUT', '60'))
        self.LIBREOFFICE_PATH = os.getenv('LIBREOFFICE_PATH', None)
        
        # HTTP 클라이언트 설정
        self.HTTP_TIMEOUT = int(os.getenv('HTTP_TIMEOUT', '30'))
        self.MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', str(100 * 1024 * 1024)))  # 100MB
        self.MAX_DOWNLOAD_SIZE = int(os.getenv('MAX_DOWNLOAD_SIZE', str(100 * 1024 * 1024)))  # 100MB
        
        # 보안 설정
        self.ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')
        
        # 로그 설정
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        self.LOG_DIR = os.getenv('LOG_DIR', f'{self.BASE_DIR}/logs')
        self.LOG_FILE = os.getenv('LOG_FILE', f'{self.LOG_DIR}/aview.log')
        self.LOG_MAX_SIZE = int(os.getenv('LOG_MAX_SIZE', str(10 * 1024 * 1024)))  # 10MB
        self.LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
        
        # 통계 스케줄러
        self.EVERY_DAY_AT = os.getenv('EVERY_DAY_AT', '03:00')
        self.EVERY_SUNDAY_AT = os.getenv('EVERY_SUNDAY_AT', '02:00')

        # 업로드 및 테스트용 파일 디렉토리
        self.FILES_DIR = os.getenv('TEST_FILES_DIR', f'{self.BASE_DIR}/files')

        # 디렉토리 생성
        self._create_directories()
        
    def _create_directories(self):
        """필요한 디렉토리들을 생성"""
        directories = [
            self.BASE_DIR,
            self.CACHE_DIR,
            self.CONVERTED_DIR,
            self.LOG_DIR,
            self.STATS_DB_PATH.rsplit('/', 1)[0] if '/' in self.STATS_DB_PATH else self.STATS_DB_PATH.rsplit('\\', 1)[0],
            self.FILES_DIR
        ]
        
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                print(f"📁 디렉토리 생성: {directory}")
    
    @property
    def redis_connection_kwargs(self):
        """Redis 연결 설정"""
        kwargs = {
            "host": self.REDIS_HOST,
            "port": self.REDIS_PORT,
            "db": self.REDIS_DB,
            "decode_responses": True
        }
        
        if self.REDIS_PASSWORD:
            kwargs["password"] = self.REDIS_PASSWORD
            
        return kwargs
    
    @property
    def is_development(self):
        """개발 환경인지 확인"""
        return self.DEBUG or self.PROFILE_NAME in ['local', 'dev', 'development']
    
    @property
    def is_production(self):
        """운영 환경인지 확인"""
        return not self.is_development and self.PROFILE_NAME in ['real', 'prod', 'production']
    
    def print_config(self):
        """설정 정보 출력 (보안 정보 제외)"""
        print("=" * 50)
        print(f"🚀 {self.APP_NAME} v{self.VERSION}")
        print("=" * 50)
        print(f"📍 Environment: {self.PROFILE_NAME}")
        print(f"🐛 Debug Mode: {self.DEBUG}")
        print(f"🌐 Server: {self.HOST}:{self.PORT}")
        print(f"📦 Redis: {self.REDIS_HOST}:{self.REDIS_PORT}")
        print(f"📁 Cache Dir: {self.CACHE_DIR}")
        print(f"📝 Log Level: {self.LOG_LEVEL}")
        print(f"📄 Log File: {self.LOG_FILE}")
        print("=" * 50)


# 전역 설정 인스턴스
settings = Config()