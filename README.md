# ComfyUI Agnes Novel Plugin
============================

Agnes AI 小说推文插件 - 集成 comfyui-agnes-ai 核心 API

## 功能

- 场景拆分 (AgnesSceneSplitter)
- 文本输入 (AgnesNovelTextSource)
- 风格选择 (AgnesStyleSelector)
- 总导演分镜 (AgnesDirectorMaster)
- 资产提取 (AgnesAssetExtractor)
- 提示词生成 (AgnesScenePromptGenerator)
- 图像生成 (AgnesImageGen)
- 文生视频 (AgnesNovelTextToVideo)
- 解说剧本生成 (AgnesScriptGenerator)
- 剧本生成·漫剧 (AgnesScreenplayGenerator)

- 分类配色：Agnes 节点在画布上按功能整体染色（配置类=琥珀 / 文本类=绿 / 图片类=蓝 / 视频类=紫，同类同色系，主体色明显带色而非近黑），且类内按 主/浅/深 三阶小幅度区分主功能、次功能、工具与中间层；由前端扩展 `web/js/agnes-node-colors.js` 实现，仍可用右键「Set color」给单个节点换色

## 依赖

- comfyui-agnes-ai (提供核心 API 客户端)
- PyYAML
- requests
- Pillow

## 安装

1. 确保已安装 comfyui-agnes-ai 插件
2. 复制本插件到 ComfyUI/custom_nodes/
3. 重启 ComfyUI
