"""
A-View 애플리케이션 설정
환경변수와 .env 파일을 통한 설정 관리
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 환경 구분
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # 애플리케이션 기본 설정
    app_name: str = Field(default="A-View Document Processor", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")
    
    # 서버 설정
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8003, env="PORT")
    reload: bool = Field(default=True, env="RELOAD")
    
    # Redis 설정
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    redis_password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    
    # 캐시 설정
    cache_dir: str = Field(default="./cache", env="CACHE_DIR")
    cache_ttl: int = Field(default=86400, env="CACHE_TTL")  # 24시간
    max_file_size: int = Field(default=100 * 1024 * 1024, env="MAX_FILE_SIZE")  # 100MB
    
    # LibreOffice 설정
    libreoffice_timeout: int = Field(default=60, env="LIBREOFFICE_TIMEOUT")
    libreoffice_path: Optional[str] = Field(default=None, env="LIBREOFFICE_PATH")
    
    # HTTP 클라이언트 설정
    http_timeout: int = Field(default=30, env="HTTP_TIMEOUT")
    max_download_size: int = Field(default=100 * 1024 * 1024, env="MAX_DOWNLOAD_SIZE")  # 100MB
    
    # 보안 설정
    allowed_origins: str = Field(default="*", env="ALLOWED_ORIGINS")
    allowed_file_types: str = Field(
        default=".doc,.docx,.odt,.rtf,.xls,.xlsx,.ods,.csv,.ppt,.pptx,.odp,.pdf",
        env="ALLOWED_FILE_TYPES"
    )
    
    # 로깅 설정
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    log_max_size: int = Field(default=10 * 1024 * 1024, env="LOG_MAX_SIZE")  # 10MB
    log_backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    @validator('allowed_origins')
    def parse_allowed_origins(cls, v):
        """CORS 허용 도메인을 리스트로 변환"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v
    
    @validator('allowed_file_types')
    def parse_allowed_file_types(cls, v):
        """허용 파일 형식을 리스트로 변환"""
        if isinstance(v, str):
            return [ext.strip().lower() for ext in v.split(',') if ext.strip()]
        return v
    
    # Pydantic v2 설정
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )
    
    def model_post_init(self, __context) -> None:
        """모델 초기화 후 처리"""
        # 환경별 .env 파일 로드
        self._load_env_files()
    
    def _load_env_files(self) -> None:
        """환경별 .env 파일 로드 (상속/오버라이드 구조)"""
        from dotenv import dotenv_values
        
        environment = os.getenv('ENVIRONMENT', 'development')
        
        # 환경별 .env 파일들 (우선순위 순 - 낮은 것부터)
        base_files = [
            '.env',                          # 기본값/공통 설정
            '.env.local',                    # 로컬 공통 설정
            f'.env.{environment}',           # 환경별 설정  
            f'.env.{environment}.local'      # 환경별 로컬 설정 (최우선)
        ]
        
        # 존재하는 파일들만 필터링
        existing_files = [f for f in base_files if Path(f).exists()]
        
        if not existing_files:
            return
        
        # 상속 구조로 설정 병합
        print(f"🔧 환경: {environment}")
        print(f"🔧 설정 파일 로딩 순서:")
        for env_file in existing_files:
            print(f"   📄 {env_file}")
            
            # dotenv로 파일 읽기
            file_settings = dotenv_values(env_file)
            
            # 환경변수에 없는 것만 설정
            for key, value in file_settings.items():
                if key and value is not None and not os.getenv(key):
                    os.environ[key] = str(value)
    
    @property
    def cache_path(self) -> Path:
        """캐시 디렉토리 경로"""
        return Path(self.cache_dir)
    
    @property
    def converted_path(self) -> Path:
        """변환된 파일 디렉토리 경로"""
        return self.cache_path / "converted"
    
    @property
    def redis_connection_kwargs(self) -> dict:
        """Redis 연결 설정"""
        if self.redis_url:
            return {"url": self.redis_url, "decode_responses": True}
        
        kwargs = {
            "host": self.redis_host,
            "port": self.redis_port,
            "db": self.redis_db,
            "decode_responses": True
        }
        
        if self.redis_password:
            kwargs["password"] = self.redis_password
            
        return kwargs
    
    def init_directories(self) -> None:
        """필요한 디렉토리 생성"""
        self.cache_path.mkdir(parents=True, exist_ok=True)
        self.converted_path.mkdir(parents=True, exist_ok=True)
        
        # 로그 디렉토리 생성
        if self.log_file:
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_development(self) -> bool:
        """개발 환경인지 확인"""
        return self.environment.lower() in ('development', 'dev') or self.debug
    
    @property
    def is_production(self) -> bool:
        """운영 환경인지 확인"""
        return self.environment.lower() in ('production', 'prod') and not self.debug


def load_settings() -> Settings:
    """환경에 맞는 설정 로드"""
    return Settings()


# 전역 설정 인스턴스
settings = load_settings()

# 설정 정보 출력 (보안 정보 제외)
def print_config_summary():
    """설정 요약 정보 출력"""
    print(f"🔧 Environment: {settings.environment}")
    print(f"🔧 Debug Mode: {settings.debug}")
    print(f"🔧 Cache Dir: {settings.cache_dir}")
    print(f"🔧 Log Level: {settings.log_level}")
    print(f"🔧 Redis: {settings.redis_host}:{settings.redis_port}")
    print(f"🔧 Server: {settings.host}:{settings.port}")

if __name__ == "__main__":
    print_config_summary()