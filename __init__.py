"""
ComfyUI Agnes Novel Plugin
===========================
小说推文工作流插件 - 集成 Agnes AI 核心 API（API 客户端内置于 api/ 模块，自包含，不依赖外部插件）
包含小说创作节点和通用 Agnes 节点，共 35 个（清单见 nodes/__init__.py）：
- 文本类 (20): API Key 配置 / API Key 池配置（多端点 Key 池 JSON，供 视频任务并发提交）/ 风格选择 / 文本输入 /
  解说剧本 / 漫剧剧本 / 场景切分 / 总导演 / 资产提取 / 文本拆分 / 资产提示词 / 资产提示词批量 /
  三视图提示词 / 三视图提示词批量 / 分镜提示词 / 分镜提示词批量 / 字符串合并 / LLM 对话
- 图片类 (7): 图像生成 / 图生图 / 三视图生成 / 三视图批量生成 / 分镜图批量生成 / 图像反推 / 图像拼图
- 视频类 (8): 文生视频 / 关键帧生视频 / 参考视频生成 / 视频任务提交 /
  视频任务并发提交（多端点 Key 池·顺序短路）/ 视频任务收取 / 视频任务批量收取 / 视频任务并发结果
"""

import os
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Web directory for frontend extensions
# web/js/ 下的前端扩展会被 ComfyUI 自动加载：
#  - agnes-node-colors.js：Agnes* 节点按功能分类配色（配置琥珀/文本绿/图片蓝/视频紫）
#  - agnes-migrate.js：批量节点旧实例（多槽输入版）widget 值自动迁移通用表
#    （分镜提示词批量 61→12；资产批量 27→8；三视图提示词批量/三视图批量 26→7），
#    规则：新 [0]=空（新合并输入槽），新 [1..K]=旧配置项尾部原样保留
WEB_DIRECTORY = "web"

print("[AgnesNovel] 已加载所有节点")

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
