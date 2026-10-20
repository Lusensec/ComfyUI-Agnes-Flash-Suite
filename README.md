# ComfyUI Agnes Novel Plugin
============================

Agnes AI 小说推文插件 - 集成 comfyui-agnes-ai 核心 API

## 功能

- 场景拆分 (AgnesSceneSplitter)
- 总导演分镜 (AgnesDirectorMaster)
- 资产提取 (AgnesAssetExtractor)
- 提示词生成 (AgnesScenePromptGenerator)
- 图像生成 (AgnesImageGen)
- 文生视频 (AgnesNovelTextToVideo)
- 剧本生成 (AgnesScriptGenerator)

- 统一配色：所有 Agnes 节点在画布上自动呈现 Agnes 蓝（标题 `#4c7dff` / 主体 `#1e2f52`），由前端扩展 `web/js/agnes-node-colors.js` 实现；仍可用右键「Set color」给单个节点换色

## 依赖

- comfyui-agnes-ai (提供核心 API 客户端)
- PyYAML
- requests
- Pillow

## 安装

1. 确保已安装 comfyui-agnes-ai 插件
2. 复制本插件到 ComfyUI/custom_nodes/
3. 重启 ComfyUI
