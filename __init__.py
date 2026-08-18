"""
ComfyUI Agnes Novel Plugin
===========================
小说推文工作流插件 - 集成 comfyui-agnes-ai 核心 API

功能：
- AgnesSceneSplitter: 场景拆分
- AgnesDirectorMaster: 总导演分镜
- AgnesAssetExtractor: 资产提取
- AgnesScenePromptGenerator: 分镜提示词生成
- AgnesImageGen: 图像生成
- AgnesVideoGen: 视频生成
- AgnesScriptGenerator: 剧本生成

依赖：
- comfyui-agnes-ai (提供 AgnesClient 和配置管理)
"""

import os

# Web directory for frontend extensions
WEB_DIRECTORY = None

# Try to import from comfyui-agnes-ai first
try:
    from ..comfyui_agnes_ai.api import (
        AgnesClient,
        get_api_key,
        BASE_URL,
        CHAT_MODEL,
        IMAGE_MODEL,
        VIDEO_MODEL,
        VIDEO_MAX_WAIT,
        VIDEO_POLL_INTERVAL,
    )
    _USES_EXTERNAL_API = True
    print("[AgnesNovel] 使用 comfyui-agnes-ai API 客户端")
except ImportError:
    # Fallback to internal API
    from .api.client import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, IMAGE_MODEL, VIDEO_MODEL
    _USES_EXTERNAL_API = False
    print("[AgnesNovel] 使用内置 API 客户端")

# Import nodes
from .nodes.scene_splitter import AgnesSceneSplitter
from .nodes.director_master import AgnesDirectorMaster
from .nodes.asset_extractor import AgnesAssetExtractor
from .nodes.prompt_generator import AgnesScenePromptGenerator
from .nodes.image_gen import AgnesImageGen
from .nodes.video_gen import AgnesVideoGen
from .nodes.script_generator import AgnesScriptGenerator

# Register nodes
NODE_CLASS_MAPPINGS = {
    "AgnesSceneSplitter": AgnesSceneSplitter,
    "AgnesDirectorMaster": AgnesDirectorMaster,
    "AgnesAssetExtractor": AgnesAssetExtractor,
    "AgnesScenePromptGenerator": AgnesScenePromptGenerator,
    "AgnesImageGen": AgnesImageGen,
    "AgnesVideoGen": AgnesVideoGen,
    "AgnesScriptGenerator": AgnesScriptGenerator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AgnesSceneSplitter": "🎬 Agnes 场景切分",
    "AgnesDirectorMaster": "🎬 Agnes 总导演",
    "AgnesAssetExtractor": "📋 Agnes 资产提取",
    "AgnesScenePromptGenerator": "🎨 Agnes 提示词生成",
    "AgnesImageGen": "🎨 Agnes 图像生成",
    "AgnesVideoGen": "🎬 Agnes 视频生成",
    "AgnesScriptGenerator": "📝 Agnes 剧本生成",
}

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
    "_USES_EXTERNAL_API",
]
