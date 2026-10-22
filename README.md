# ComfyUI Agnes Flash Suite
===========================

Agnes AI 全能力 ComfyUI 节点套件 — 27 个节点：LLM 文本管线（小说/分镜/剧本/解说/漫剧，分镜提示词 50 路批量）、文生图/图生图/三视图（单张+20 路批量）/分镜图 50 路批量生成，以及文生视频/关键帧生视频/参考视频生成。批量节点全部支持 JSON 合并输入/输出（文本拆分 all_items → 资产提示词批量 all_items→all_prompts → 三视图提示词批量 all_prompts→all_turnaround_prompts → 三视图批量 all_prompts→all_images → 图像拼图 batch_images），全链路一根线到底，免逐槽手接。

## 功能

文本类（17 个）：

- 🔑 Agnes API Key 配置
- 🪄 Agnes 风格选择（视觉风格 × 导演风格双轴，纯本地组合）
- 📥 Agnes 文本输入（管线文本起点）
- 📝 Agnes 解说剧本生成（影视解说文案/口播稿）
- 🎭 Agnes 剧本生成（漫剧短视频分场剧本：钩子+画面/对白/氛围）
- 🎬 Agnes 场景切分（小说章节/剧本 → 5 秒场景段落 ×50 + 全文合并（JSON 数组））
- 🎬 Agnes 总导演（章节/剧本→分镜，最多 50 组 + 分镜总数 + 全文合并（JSON 数组））
- 📋 Agnes 资产提取（角色/物品/场景清单）
- ✂️ Agnes 文本拆分（按条数/字数/段落拆分，最多 20 条 + all_items 全部条目 JSON 输出（可一根线直连 批量节点合并输入））
- 🖌️ Agnes 资产提示词生成（角色/物品/场景三档定妆提示词）
- 🖌️ Agnes 资产提示词批量生成（all_items 合并输入（JSON 数组，直连 资产提取 5 路 JSON / 文本拆分 all_items，免 20 路手接）并发生成英文提示词，输出 20 路提示词 + 整批执行状态 JSON + all_prompts 全部提示词 JSON 数组（可直连 三视图提示词批量生成），线程池速率可限，默认 10）
- ✍️ Agnes 三视图提示词生成（左 1/3 特写 + 右 2/3 三视图分栏布局）
- ✍️ Agnes 三视图提示词批量生成（all_prompts 合并输入（JSON 数组，直连 资产提示词批量 all_prompts 输出，免 20 路手接）并发生成三视图提示词，输出 20 路提示词 + 整批执行状态 JSON + all_turnaround_prompts 全部三视图提示词 JSON 数组（可直连 三视图批量生成），线程池速率可限，默认 10）
- 🎨 Agnes 分镜提示词生成（单帧画面提示词，可注入 资产提取 角色/场景/服装/道具/天气 5 路 JSON）
- 🎨 Agnes 分镜提示词批量生成（all_scenes 合并输入（JSON 数组）并发生成英文提示词，对应 总导演/场景切分 all_scenes 输出，单条分镜纯文本也接受，可整批注入资产 5 路 JSON，输出 50 路提示词 + 整批执行状态 JSON + all_prompts 全部提示词 JSON 数组（可直连 分镜图批量生成），线程池速率可限，默认 10）
- 🔗 Agnes 字符串合并
- 💬 Agnes LLM 对话（3.0/2.5 思考档位可切）

图片类（7 个）：

- 🎨 Agnes 图像生成（文生图）
- 🖼️ Agnes 图生图
- 📐 Agnes 三视图生成
- 📐 Agnes 三视图批量生成（all_prompts 合并输入（JSON 数组，直连 三视图提示词批量 all_turnaround_prompts 输出，免 20 路手接）并发出图，输出 20 路图 + 整批执行状态 JSON + all_images 批量图张量 (N,H,W,3)（可直连 图像拼图 总输入一根线出总览），线程池速率可限，默认 10）
- 🎞️ Agnes 分镜图批量生成（all_prompts 合并输入（JSON 数组）并发出分镜关键帧，对应 分镜提示词批量 all_prompts 输出，单条提示词纯文本也接受，画质档位/宽高比可配，整批执行状态 JSON 输出，线程池速率可限，默认 10）
- 🔍 Agnes 图像反推提示词
- 🧩 Agnes 图像拼图（batch_images 批量张量总输入（三视图批量/分镜图批量 all_images 直连，优先于 20 槽）或 20 路批量图 → 1 张 2 列网格拼图，自动跳过黑图占位，N 动态定行数，纯本地）

视频类（3 个）：

- 🎞️ Agnes 文生视频
- 🎬 Agnes 关键帧生视频（首尾帧）
- 🎞️ Agnes 参考视频生成

前端特性：

- 分类配色：Agnes 节点在画布上按功能整体染色（配置类=琥珀 / 文本类=绿 / 图片类=蓝 / 视频类=紫，同类同色系，主体色明显带色而非近黑），且类内按 主/浅/深 三阶小幅度区分主功能、次功能、工具与中间层；由前端扩展 `web/js/agnes-node-colors.js` 实现，仍可用右键「Set color」给单个节点换色
- 旧实例自愈：分镜提示词批量生成节点输入结构升级（50 槽 → all_scenes 单输入）后，旧工作流实例的 widget 值在载入/排队时自动重映射（`web/js/agnes-migrate.js`），避免「Value not in list」类校验报错

## 依赖

本套件**自包含**，API 客户端已内置于 `api/` 模块（AgnesClient，chat/images/video 三类端点），**不再依赖外部 comfyui-agnes-ai 插件**（旧版 README 中「comfyui-agnes-ai 提供核心 API 客户端」的说法已过时，该包的相关功能已并入本套件）。

- ComfyUI 本体即提供全部第三方库（requests / PyYAML / Pillow / numpy / torch / folder_paths），无需额外 pip 安装
- Python 3.10+

## 安装

1. 克隆本插件到 `ComfyUI/custom_nodes/`：
   ```powershell
   cd "你的ComfyUI路径\ComfyUI\custom_nodes"
   git clone https://github.com/Lusensec/Comfyui-Agnes-Flash-Suite.git
   ```
   或下载 ZIP 解压为 `ComfyUI/custom_nodes/Comfyui-Agnes-Flash-Suite/`
2. 重启 ComfyUI

## 配置 API Key

三种方式（可混用，优先级从高到低）：

1. 节点输入：在节点的 `api_key` 输入框直接填写
2. 环境变量：`AGNES_API_KEY`
3. 文件：`api_key_config.json`（由「🔑 Agnes API Key 配置」节点写入/缓存）

也可在内置 `config.yaml` 的 `api_key` 字段填写（优先级最低）。

## 配置

内置 `config.yaml` 可覆盖：

- `api.base_url`：默认 `https://api.agnes-ai.cn/v1`
- `api.video_max_wait` / `api.video_poll_interval`：视频生成轮询等待
- `models.chat` / `models.image` / `models.video`：默认模型
- `api_key`：默认 Key

## 节点详细说明

- [NODE_GUIDE.md](NODE_GUIDE.md)：每个节点的用法、管线示例与排错
- [INSTALL.md](INSTALL.md)：安装与配置指南
