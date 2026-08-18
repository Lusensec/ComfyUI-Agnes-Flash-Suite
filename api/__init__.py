"""
Agnes AI API Client Module
===========================
提供核心 API 客户端和配置管理

依赖：
- 优先使用 comfyui-agnes-ai 插件的 API
- 如果未安装，使用内置的 fallback API
"""

import os

# 尝试从 comfyui-agnes-ai 导入
_COMFYUI_AGNES_AI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "comfyui-agnes-ai",
    "api",
    "__init__.py"
)

if os.path.exists(_COMFYUI_AGNES_AI_PATH):
    try:
        # 动态导入 comfyui-agnes-ai 的 API
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "comfyui_agnes_ai_api",
            _COMFYUI_AGNES_AI_PATH
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 导出所有公开接口
        AgnesClient = module.AgesClient
        get_api_key = module.get_api_key
        set_api_key = module.set_api_key
        BASE_URL = module.BASE_URL
        CHAT_MODEL = module.CHAT_MODEL
        IMAGE_MODEL = module.IMAGE_MODEL
        VIDEO_MODEL = module.VIDEO_MODEL
        VIDEO_MAX_WAIT = module.VIDEO_MAX_WAIT
        VIDEO_POLL_INTERVAL = module.VIDEO_POLL_INTERVAL
        
        _USES_EXTERNAL_API = True
        print("[AgnesAPI] 使用 comfyui-agnes-ai API 客户端")
    except Exception as e:
        print(f"[AgnesAPI] 导入 comfyui-agnes-ai 失败: {e}，使用内置 API")
        _USES_EXTERNAL_API = False
else:
    # 使用内置 fallback API
    from .client import (
        AgnesClient,
        get_api_key,
        set_api_key,
        BASE_URL,
        CHAT_MODEL,
        IMAGE_MODEL,
        VIDEO_MODEL,
        VIDEO_MAX_WAIT,
        VIDEO_POLL_INTERVAL,
    )
    _USES_EXTERNAL_API = False
    print("[AgnesAPI] 使用内置 API 客户端")

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
    "_USES_EXTERNAL_API",
]
