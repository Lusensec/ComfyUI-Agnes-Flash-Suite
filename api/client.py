"""
Agnes AI API Client (Fallback)
===============================
当 comfyui-agnes-ai 未安装时使用的备用 API 客户端

主要功能：
- AgnesClient: API 客户端类
- get_api_key(): 获取 API Key
- BASE_URL/CHAT_MODEL/IMAGE_MODEL/VIDEO_MODEL: 配置常量
"""

import requests
import yaml
import json
import os
import time
from typing import Any, Dict, List, Optional


# 配置路径
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.yaml")

# 默认配置
DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_CHAT_MODEL = "agnes-2.5-flash"
DEFAULT_IMAGE_MODEL = "agnes-image-2.1-flash"
DEFAULT_VIDEO_MODEL = "agnes-video-v2.0"
DEFAULT_VIDEO_MAX_WAIT = 600
DEFAULT_VIDEO_POLL_INTERVAL = 10


def _load_config() -> Dict[str, Any]:
    """从 config.yaml 加载配置"""
    config = {
        "base_url": DEFAULT_BASE_URL,
        "chat_model": DEFAULT_CHAT_MODEL,
        "image_model": DEFAULT_IMAGE_MODEL,
        "video_model": DEFAULT_VIDEO_MODEL,
        "video_max_wait": DEFAULT_VIDEO_MAX_WAIT,
        "video_poll_interval": DEFAULT_VIDEO_POLL_INTERVAL,
        "api_key": "",
    }
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config and "api" in yaml_config:
                    if "base_url" in yaml_config["api"]:
                        config["base_url"] = yaml_config["api"]["base_url"]
                    if "video_max_wait" in yaml_config["api"]:
                        config["video_max_wait"] = int(yaml_config["api"]["video_max_wait"])
                    if "video_poll_interval" in yaml_config["api"]:
                        config["video_poll_interval"] = int(yaml_config["api"]["video_poll_interval"])
                    if "models" in yaml_config:
                        if "chat" in yaml_config["models"]:
                            config["chat_model"] = yaml_config["models"]["chat"]
                        if "image" in yaml_config["models"]:
                            config["image_model"] = yaml_config["models"]["image"]
                        if "video" in yaml_config["models"]:
                            config["video_model"] = yaml_config["models"]["video"]
                if "api_key" in yaml_config:
                    config["api_key"] = yaml_config["api_key"] or ""
    except Exception as e:
        print(f"[AgnesAPI] 配置加载失败: {e}")
    return config


_config = _load_config()

# 导出配置
BASE_URL = _config["base_url"]
CHAT_MODEL = _config["chat_model"]
IMAGE_MODEL = _config["image_model"]
VIDEO_MODEL = _config["video_model"]
VIDEO_MAX_WAIT = _config["video_max_wait"]
VIDEO_POLL_INTERVAL = _config["video_poll_interval"]


# API Key 管理
_API_KEY_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "api_key_config.json")
_GLOBAL_CONFIG: Dict[str, Any] = {
    "api_key": os.environ.get("AGNES_API_KEY", "") or _config.get("api_key", ""),
}


def _load_key_from_config_file() -> str:
    """从配置文件加载 API Key"""
    try:
        if os.path.exists(_API_KEY_CONFIG_FILE):
            with open(_API_KEY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("api_key", "")
    except Exception:
        pass
    return ""


# 初始化 API Key
if not _GLOBAL_CONFIG["api_key"]:
    _GLOBAL_CONFIG["api_key"] = _load_key_from_config_file() or _config.get("api_key", "")


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) > 12:
        return key[:8] + "****" + key[-4:]
    elif len(key) > 6:
        return key[:3] + "****" + key[-3:]
    return "****"

def get_api_key() -> str:
    """获取当前 API Key"""
    # 1. Env var has highest priority
    key = os.environ.get("AGNES_API_KEY", "").strip()
    if key:
        print(f"[AgnesAPI] API Key source: env var AGNES_API_KEY = {_mask_key(key)}")
        return key
    # 2. Try to load from api_key_config.json
    key = _load_key_from_config_file()
    if key:
        _GLOBAL_CONFIG["api_key"] = key
        print(f"[AgnesAPI] API Key source: api_key_config.json = {_mask_key(key)}")
        return key
    # 3. Try to load from config.yaml
    yaml_key = _config.get("api_key", "").strip()
    if yaml_key:
        _GLOBAL_CONFIG["api_key"] = yaml_key
        print(f"[AgnesAPI] API Key source: config.yaml = {_mask_key(yaml_key)}")
        return yaml_key
    # 4. Fallback to cached value
    cached = _GLOBAL_CONFIG["api_key"].strip()
    if cached:
        print(f"[AgnesAPI] API Key source: global cache = {_mask_key(cached)}")
    else:
        print("[AgnesAPI] No API Key found in any source (env var, api_key_config.json, config.yaml, cache)")
    return cached


def set_api_key(key: str) -> None:
    """设置 API Key"""
    _GLOBAL_CONFIG["api_key"] = key
    # 保存到配置文件
    try:
        config_data = {"api_key": key}
        os.makedirs(os.path.dirname(_API_KEY_CONFIG_FILE), exist_ok=True)
        with open(_API_KEY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class AgnesClient:
    """Agnes AI API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = CHAT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> str:
        """调用聊天补全 API"""
        url = f"{BASE_URL}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        
        resp = self.session.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def generate_image(
        self,
        prompt: str,
        model: str = IMAGE_MODEL,
        size: str = "1024x1024",
        n: int = 1,
    ) -> List[str]:
        """生成图像"""
        url = f"{BASE_URL}/images/generations"
        payload = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "n": n,
        }
        
        resp = self.session.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        
        images = []
        for item in data.get("data", []):
            image_url = item.get("url") or item.get("image_url")
            if image_url:
                images.append(image_url)
        
        return images

    def generate_video(
        self,
        prompt: str,
        model: str = VIDEO_MODEL,
        num_frames: int = 121,
        frame_rate: int = 24,
        width: int = 1920,
        height: int = 1080,
        max_wait: int = None,
    ) -> Dict[str, Any]:
        """生成视频（异步）"""
        if max_wait is None:
            max_wait = VIDEO_MAX_WAIT
        
        url = f"{BASE_URL}/videos"
        payload = {
            "model": model,
            "prompt": prompt,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
            "width": width,
            "height": height,
        }
        
        # 提交任务
        resp = self.session.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        
        task_id = data.get("id")
        video_id = data.get("video_id", task_id)
        
        if not task_id:
            raise Exception(f"未获取到任务ID: {data}")
        
        # 轮询查询结果
        poll_url = f"{BASE_URL}/agnesapi?video_id={video_id}"
        elapsed = 0
        
        while elapsed < max_wait:
            time.sleep(VIDEO_POLL_INTERVAL)
            elapsed += VIDEO_POLL_INTERVAL
            
            status_resp = self.session.get(poll_url, timeout=30)
            if status_resp.status_code != 200:
                continue
            
            status_data = status_resp.json()
            state = status_data.get("status")
            
            if state == "completed":
                video_url = None
                for key in ("video_url", "url", "output_url", "download_url"):
                    val = status_data.get(key)
                    if val and isinstance(val, str) and val.startswith("http"):
                        video_url = val
                        break
                
                if video_url:
                    return {"video_url": video_url, "video_id": video_id, "task_id": task_id}
                else:
                    raise Exception("未找到视频 URL")
            
            elif state in ("failed", "error"):
                error_msg = status_data.get("error", "Unknown error")
                raise Exception(f"视频生成失败: {error_msg}")
        
        raise Exception(f"视频生成超时 ({max_wait}s)")


# 导出
__all__ = [
    "AgnesClient",
    "get_api_key",
    "set_api_key",
    "BASE_URL",
    "CHAT_MODEL",
    "IMAGE_MODEL",
    "VIDEO_MODEL",
    "VIDEO_MAX_WAIT",
    "VIDEO_POLL_INTERVAL",
]
