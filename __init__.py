"""
ComfyUI Agnes Novel Plugin
===========================
小说推文工作流插件 - 集成 Agnes AI 核心 API
包含小说创作节点和通用 Agnes 节点

功能：
- Novel 专用节点:
  * AgnesSceneSplitter: 场景拆分
  * AgnesDirectorMaster: 总导演分镜
  * AgnesAssetExtractor: 资产提取
  * AgnesScenePromptGenerator: 分镜提示词生成
  * AgnesImageGen: 图像生成
  * AgnesNovelTextToVideo: 文生视频（原 AgnesVideoGen 已删除）
  * AgnesScriptGenerator: 解说剧本生成（影视解说文案/口播稿）
  * AgnesScreenplayGenerator: 剧本生成（漫剧短视频分场剧本：钩子+画面/对白/氛围）
- 通用节点（从 comfyui-agnes-ai 集成）:
  * AgnesAPIKeyConfig: API Key 配置
  * AgnesTextSource: 文本输入（小说章节/故事想法，管线文本起点）
  * AgnesLLMChat: LLM 对话
  * AgnesImageReverse: 图像反转
  * AgnesImageToImage: 图生图
  * AgnesTextToImage: 文生图
  * AgnesImageToVideo: 图生视频
  * AgnesTextToVideo: 文生视频
"""

import os
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Web directory for frontend extensions
# web/js/ 下的前端扩展（节点配色等）会被 ComfyUI 自动加载：
#  - 服务端 /extensions 列表包含 web/js/agnes-node-colors.js
#  - 前端启动时 import 并注册，Agnes* 节点自动获得 Agnes 蓝配色
WEB_DIRECTORY = "web"

print("[AgnesNovel] 已加载所有节点")

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
