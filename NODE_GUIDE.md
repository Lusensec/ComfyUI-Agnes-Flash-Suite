# 🎬 Agnes Novel 插件 - 节点配置指南

## 快速开始

### 1. 获取 API Key
访问 https://platform.agnes-ai.com 注册并获取 API Key

### 2. 安装插件
```powershell
Expand-Archive -Path "comfyui-agnes-novel.zip" -DestinationPath "你的ComfyUI路径\ComfyUI\custom_nodes\" -Force
```

### 3. 重启 ComfyUI

### 4. 动态请求地址（Base URL）

所有节点均带 `base_url` 输入框，**留空 = 跟随全局动态值**。优先级（高→低）：

1. 节点内 `base_url` 输入框（单节点覆盖）
2. API Key 配置节点保存的 `api_key_config.json`（全局）
3. 环境变量 `AGNES_API_BASE_URL`
4. `config.yaml` 的 `api.base_url`
5. 内置默认 `https://api.agnes-ai.cn/v1`

> **布局约定**：为贴近"请求地址 + 密钥"这一组配置，`base_url` 统一放在
> **`api_key` 紧挨着的上方**（二者相邻），且位于提示词/内容输入之后，
> 不再顶在最上面与内容区混在一起。

### 5. 输出描述机制

ComfyUI 节点规格中，**输入（widgets）自带 tooltip/placeholder/label 描述机制**，
而**输出只有短标签（RETURN_NAMES/RETURN_LABELS）**。本插件通过两条官方扩展点补齐
输出的"描述"，使其在节点文档面板的"输出 → 描述"列可见：

- **`OUTPUT_TOOLTIPS`**（类属性，与 `RETURN_NAMES` 一一对应）：ComfyUI 内核
  `server.py` 读取该属性并以 `output_tooltips` 字段随节点定义下发前端，
  节点文档面板"输出"表格的"描述"列、以及输出接口的悬停提示都读它。
  各节点已逐一填写；mixin 节点由 `nodes/_output_docs.py` 的元类从
  `OUTPUT_DOCS` 自动生成，避免重复维护。
- **`get_extra_output_methods()` / `get_extra_pnginfo()`**：保存图像/视频时
  把每个输出的含义写入文件元数据（PNG info / 文件说明），可在 ComfyUI
  画廊或任意 PNG-info 工具中查看。
- 共享实现见 `nodes/_output_docs.py`（OutputDocsMixin + OutputDocsMeta）。

### 6. Agnes API 参数可用性对照（生图/生视频参数与真实 API 参数的对应关系）

| 节点参数 | 新图像接口 image-2.5-flash | 旧图像接口 2.1/2.0 | 新视频接口 video-2.5-flash | 旧视频接口 v2.0 |
|---|---|---|---|---|
| model | ✅ | ✅ | ✅ | ✅ |
| prompt | ✅ | ✅ | ✅ | ✅ |
| 尺寸 | size 档位 1K/2K/3K/4K + ratio | width/height(WxH) | aspect_ratio（固定 720P） | width/height(WxH) |
| n（张数） | ❌ API 不支持，固定 1 张 | ✅ 1-4 | ❌ 固定 1 | - |
| seed（种子） | ❌ | ❌ | ✅ 可选（0=随机） | ✅ 可选 |
| strength（强度） | ❌ 无此参数，节点将其转成提示词指令 | 同左 | - | - |
| 时长 | - | - | seconds "4"~"12"（节点用 帧数/帧率 换算） | num_frames（8n+1） |
| frame_rate | - | - | ❌ API 无此参数 | ✅ 传给 API |
| quality | 即 size 档位 | 1K/2K | ❌ 固定 720P，无此参数 | 映射 WxH 像素 |
| max_wait | 客户端轮询超时，非 API 参数 | 同左 | 同左 | 同左 |

> 结论：新 2.5 系列模型**不再支持 n/strength/seed（图）/frame_rate（视）等参数**，
> 节点中保留这些输入框是为了兼容旧模型和习惯；使用新模型时它们不生效（已在各
> widget 的 tooltip 中注明）。视频 2.5 支持 seed，可直接传入做可复现实验。

---

## 节点配置说明

### 🎬 Agnes 场景切分 (AgnesSceneSplitter)

**功能：** 将小说章节拆分为 5 秒/片的场景段落

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 小说章节文本，建议 3000-8000 字 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| model | STRING | agnes-2.5-flash | 文本生成模型 |

**输出：**
- log_text: 处理日志
- scene_1 ~ scene_50: 最多 50 个场景片段
- chapter_text_out: 原文本（透传）
- api_key_out / base_url_out / model_out: 配置透传

---

### 🎬 Agnes 总导演 (AgnesDirectorMaster)

**功能：** 生成完整编号分镜脚本

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 小说章节文本 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| model | STRING | agnes-2.5-flash | 文本生成模型 |

**输出：**
- log_text: 处理日志
- scene_1 ~ scene_50: 分镜脚本
- chapter_text_out / api_key_out / base_url_out / model_out: 透传

---

### 📋 Agnes 资产提取 (AgnesAssetExtractor)

**功能：** 提取角色、场景、道具等资产信息

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 小说章节文本 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| model | STRING | agnes-2.5-flash | 文本生成模型 |

**输出：**
- characters_json: 角色信息 JSON
- locations_json: 场景信息 JSON
- props_json: 道具列表 JSON
- costumes_json: 服装信息 JSON
- weather_json: 天气信息 JSON

---

### 🎨 Agnes 分镜提示词生成 (AgnesScenePromptGenerator)

**功能：** 将分镜脚本转换为英文生图提示词

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| scene_text | STRING | "" | 分镜文本（从场景切分或总导演获取） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| style | COMBO | cinematic | 图像风格：cinematic/anime/realistic/watercolor/oil_painting |
| characters_json | STRING | "" | 角色信息 JSON（可选） |
| locations_json | STRING | "" | 场景信息 JSON（可选） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| model | STRING | agnes-2.5-flash | 文本生成模型 |

**输出：**
- detailed_prompt: 英文提示词

---

### 🎨 Agnes 图像生成 (AgnesImageGen)

**功能：** 根据提示词生成场景图像

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| prompt | STRING | "" | 英文图像描述 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| width | INT | 1920 | 图像宽度（旧接口 WxH 像素；新接口 agnes-image-2.5-flash 自动映射到支持的比例） |
| height | INT | 1080 | 图像高度（同上） |
| quality | COMBO | 1K | 画质档位：1K/2K/3K/4K（新图像模型 agnes-image-2.5-flash 按档位出图，2K 性价比最高） |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型，可选 2.5-flash / 2.1-flash / 2.0-flash（选旧模型时 width/height 按像素生效） |

**输出（含输出描述）：**
- image: 图像张量（连接视频生成节点或 SaveImage）
- url: 图片 URL（保存的文件路径/下载 URL）

---

### 🎬 Agnes 视频生成 (AgnesVideoGen)

**功能：** 图生视频 / 文生视频

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| prompt | STRING | "" | 视频描述（可选） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型，可选 2.5-flash（4-12s/720P）/ agnes-video-v2.0（帧数模式） |
| num_frames | INT | 121 | 旧接口帧数（121≈5秒 @ 24fps）；新接口自动换算为秒数（4-12s） |
| frame_rate | INT | 24 | 帧率（旧接口生效；新接口仅用于换算时长，API 无此参数） |
| quality | COMBO | 1K | 画质（旧接口 1K/2K；新接口固定 720P，API 无此参数） |
| aspect_ratio | COMBO | 16:9 | 宽高比：16:9/9:16/1:1/4:3/3:4 |
| image | IMAGE | - | 参考图片（可选；连接后走图生视频） |

**输出（含输出描述）：**
- video: 视频文件路径（MP4 保存到 ComfyUI output/agnes_videos/）
- video_id: 视频任务唯一标识（可用于查询重试）
- task_id: API 返回的任务 ID

---

### 📝 Agnes 剧本生成 (AgnesScriptGenerator)

**功能：** 生成影视解说文案

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| story_outline | STRING | "" | 故事大纲 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| style | COMBO | casual | 解说风格：casual/professional/humorous/dramatic |
| target_duration | INT | 180 | 目标时长（秒） |
| temperature | FLOAT | 0.8 | 生成温度（0-1） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| model | STRING | agnes-2.5-flash | 文本生成模型 |

**输出：**
- script: 解说文案

---

### 📐 Agnes 角色三视图设定图 (AgnesNovelCharacterTurnaround)

**功能：** 生成角色三视图设定表（turnaround sheet）：同一角色正面/侧面/背面从左到右并排，全身正交视图、比例与服装发型细节一致

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| character_desc | STRING | "" | 角色名 + 外貌/服装描述（越具体越一致） |
| api_key | STRING | 留空自动加载 | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型 |
| quality | COMBO | 2K | 档位：1K/2K/3K/4K |
| aspect_ratio | COMBO | 21:9 | 三视图推荐宽幅 21:9 / 16:9 |
| reference_image | IMAGE | - | 可选：角色定妆图，连接后走图生图保持一致 |
| extra_prompt | STRING | "" | 可选：追加风格/质量补充词 |

**输出：**
- image: 三视图张量（可存图或作为后续视频节点参考）
- resolution: 实际分辨率
- final_prompt: 最终拼接的完整提示词

---

## 推荐配置

### 快速测试
- 使用精简工作流 `agnes-novel-minimal.json`
- 只配置 API Key
- 输入一段小说文本

### 完整流程
1. **场景切分** → 获取 scene_1
2. **资产提取** → 获取 characters_json, locations_json
3. **提示词生成** → 连接 scene_1 + characters_json + locations_json
4. **图像生成** → 生成场景图像
5. **视频生成** → 连接图像，生成视频
6. **剧本生成** → 独立流程，生成解说文案

---

## 成本估算

| 操作 | 单价估算 | 单集成本 (20场景) |
|------|----------|-------------------|
| LLM 调用 | ~0.001 USD | ~0.10 USD |
| 图像生成 | ~0.01 USD | ~0.20 USD |
| 视频生成 | ~0.10 USD | ~2.00 USD |
| **总计** | | **~2.30 USD** |

Starter 档位 ($4/月) 可支持约 1-2 集/天

---

## 故障排除

### API 认证失败 (401)
- 检查 API Key 是否正确
- 确认账户余额充足
- 访问 https://platform.agnes-ai.com 检查配额

### 视频生成超时
- 查看错误信息中的 video_id
- 尝试降低画质 (1K) 或减少帧数 (121→81)
- 稍后重试（服务器可能繁忙）

### 图像生成质量差
- 优化提示词（添加质量词：masterpiece, best quality, 8k）
- 尝试不同的 aspect_ratio
- 使用 2K 画质

---

## 输出文件位置

| 类型 | 位置 |
|------|------|
| 分镜脚本 | `%USERPROFILE%\Documents\AgnesOutput\` |
| 视频文件 | `ComfyUI/output/agnes_videos/` |

---

**版本**: 1.1.0  
**更新日期**: 2026-10-19
