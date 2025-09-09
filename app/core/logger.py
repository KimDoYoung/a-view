import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from app.core.config import settings
import os

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(settings.LOG_LEVEL)
    LOG_FILE = settings.LOG_FILE
    
    # 로그 디렉토리 생성
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    if not logger.handlers:
        file_handler = ConcurrentRotatingFileHandler(
            LOG_FILE, "a", 5*1024*1024, 7, encoding='utf-8'
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        if settings.PROFILE_NAME == "local":
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    return logger

# 로그 파일 읽기 함수 추가
def read_log_file(lines=1000):
    """로그 파일의 마지막 N줄을 읽어옵니다."""
    try:
        with open(settings.LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            return all_lines[-lines:] if len(all_lines) > lines else all_lines
    except FileNotFoundError:
        return ["로그 파일을 찾을 수 없습니다."]
    except Exception as e:
        return [f"로그 파일 읽기 오류: {str(e)}"]