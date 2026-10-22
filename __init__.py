"""
ComfyUI Agnes Novel Plugin
===========================
小说推文工作流插件 - 集成 Agnes AI 核心 API（API 客户端内置于 api/ 模块，自包含，不依赖外部插件）
包含小说创作节点和通用 Agnes 节点，共 26 个（清单见 nodes/__init__.py）：
- 文本类 (17): API Key 配置 / 风格选择 / 文本输入 / 解说剧本 / 漫剧剧本 /
  场景切分 / 总导演 / 资产提取 / 文本拆分 / 资产提示词 / 资产提示词批量 /
  三视图提示词 / 三视图提示词批量 / 分镜提示词 / 分镜提示词批量 / 字符串合并 / LLM 对话
- 图片类 (6): 图像生成 / 图生图 / 三视图生成 / 三视图批量生成 / 图像反推 / 图像拼图
- 视频类 (3): 文生视频 / 关键帧生视频 / 参考视频生成
"""

import os
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Web directory for frontend extensions
# web/js/ 下的前端扩展会被 ComfyUI 自动加载：
#  - agnes-node-colors.js：Agnes* 节点按功能分类配色（配置琥珀/文本绿/图片蓝/视频紫）
#  - agnes-migrate.js：分镜提示词批量节点旧实例（61 输入版）widget 值 61→12 槽自动迁移
WEB_DIRECTORY = "web"

print("[AgnesNovel] 已加载所有节点")

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
