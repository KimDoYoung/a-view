import platform
import socket
import psutil
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import uuid

class SystemInfo:
    def __init__(self):
        self._cache = {}
        self._cache_time = None
    
    def get_system_info(self, force_refresh=False) -> Dict[str, Any]:
        """시스템 정보를 빠르게 수집 (캐싱 사용)"""
        now = datetime.now()
        
        # 5분 캐시
        if not force_refresh and self._cache_time and (now - self._cache_time).seconds < 300:
            return self._cache
        
        info = {
            "timestamp": now.isoformat(),
            "environment": self._detect_environment(),
            "basic": self._get_basic_info(),
            "network": self._get_network_info(),
            "hardware": self._get_hardware_info(),
            "containers": self._check_container_env()
        }
        
        self._cache = info
        self._cache_time = now
        return info
    
    def _detect_environment(self) -> str:
        """환경 타입 감지"""
        # Docker 환경 체크
        if Path("/.dockerenv").exists():
            return "docker"
        
        # 다른 컨테이너 환경 체크
        if os.path.exists("/proc/1/cgroup"):
            try:
                with open("/proc/1/cgroup", "r") as f:
                    content = f.read()
                    if "docker" in content:
                        return "docker"
                    elif "kubepods" in content:
                        return "kubernetes"
                    elif "lxc" in content:
                        return "lxc"
            except:
                pass
        
        # Windows 환경
        if platform.system() == "Windows":
            return "windows_local"
        
        # Linux/Mac 로컬
        return "local"
    
    def _get_basic_info(self) -> Dict[str, Any]:
        """기본 시스템 정보 (빠름)"""
        return {
            "os": platform.system(),
            "os_version": platform.release(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "user": os.getenv("USER") or os.getenv("USERNAME", "unknown")
        }
    
    def _get_network_info(self) -> Dict[str, Any]:
        """네트워크 정보 (적당히 빠름)"""
        try:
            # 로컬 IP (빠름)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # MAC 주소 (빠름)
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0,2*6,2)][::-1])
            
            return {
                "local_ip": local_ip,
                "mac_address": mac,
                "is_localhost": local_ip.startswith("127.") or local_ip.startswith("::1")
            }
        except:
            return {
                "local_ip": "unknown",
                "mac_address": "unknown", 
                "is_localhost": False
            }
    
    def _get_hardware_info(self) -> Dict[str, Any]:
        """하드웨어 정보 (적당한 속도)"""
        try:
            # CPU 정보
            cpu_count = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            
            # 메모리 정보 (빠름)
            memory = psutil.virtual_memory()
            
            # 디스크 정보 (보통)
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_cores": cpu_count_physical,
                "cpu_threads": cpu_count,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "memory_percent": memory.percent,
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "disk_percent": round((disk.used / disk.total) * 100, 2)
            }
        except:
            return {
                "cpu_cores": "unknown",
                "cpu_threads": "unknown",
                "memory_total_gb": "unknown",
                "memory_available_gb": "unknown",
                "memory_percent": "unknown",
                "disk_total_gb": "unknown",
                "disk_free_gb": "unknown",
                "disk_percent": "unknown"
            }
    
    def _check_container_env(self) -> Dict[str, Any]:
        """컨테이너 환경 상세 체크"""
        container_info = {
            "is_container": False,
            "container_type": None,
            "container_id": None
        }
        
        try:
            # Docker 환경 체크
            if Path("/.dockerenv").exists():
                container_info["is_container"] = True
                container_info["container_type"] = "docker"
                
                # Docker container ID 추출 시도
                try:
                    with open("/proc/self/cgroup", "r") as f:
                        for line in f:
                            if "docker" in line:
                                container_info["container_id"] = line.split("/")[-1].strip()[:12]
                                break
                except:
                    pass
            
            # Kubernetes 환경 체크
            if os.path.exists("/var/run/secrets/kubernetes.io"):
                container_info["is_container"] = True
                container_info["container_type"] = "kubernetes"
                
        except:
            pass
        
        return container_info
    
    def get_environment_summary(self) -> str:
        """환경 요약 문자열"""
        info = self.get_system_info()
        
        env_type = info["environment"]
        hostname = info["basic"]["hostname"]
        os_name = info["basic"]["os"]
        ip = info["network"]["local_ip"]
        
        if env_type == "docker":
            container_id = info["containers"].get("container_id", "unknown")
            return f"Docker({container_id}) on {os_name} - {ip}"
        elif env_type == "kubernetes":
            return f"K8s on {hostname} - {ip}"
        elif env_type == "windows_local":
            return f"Windows Local - {hostname} ({ip})"
        else:
            return f"Local - {hostname} ({ip})"
    
    def is_development_env(self) -> bool:
        """개발 환경 여부 판단"""
        info = self.get_system_info()
        
        # Docker가 아닌 로컬 환경
        if info["environment"] in ["local", "windows_local"]:
            return True
        
        # Docker이지만 로컬호스트 IP
        if info["environment"] == "docker" and info["network"]["is_localhost"]:
            return True
        
        return False

# 전역 인스턴스
system_info = SystemInfo()

# 편의 함수들
def get_system_info():
    return system_info.get_system_info()

def get_environment_summary():
    return system_info.get_environment_summary()

def is_development_env():
    return system_info.is_development_env()

def get_quick_env_info():
    """빠른 환경 정보 (대시보드용)"""
    info = system_info.get_system_info()
    return {
        "environment": info["environment"],
        "hostname": info["basic"]["hostname"],
        "os": info["basic"]["os"],
        "ip": info["network"]["local_ip"],
        "memory_usage": f"{info['hardware']['memory_percent']}%",
        "disk_usage": f"{info['hardware']['disk_percent']}%",
        "summary": system_info.get_environment_summary()
    }