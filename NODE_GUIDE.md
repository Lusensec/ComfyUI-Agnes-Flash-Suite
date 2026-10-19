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
| 尺寸 | size 档位 1K/2K/3K/4K | width/height(WxH) | 固定 720P | width/height(WxH) |
| ratio（宽高比） | ✅ 1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9（默认 1:1），与档位组合决定像素，节点已提供 aspect_ratio 下拉 | ❌ 按 WxH 像素表达 | ✅ 16:9/9:16/1:1/4:3/3:4 | ✅ 映射 WxH 像素 |
| n（张数） | ❌ API 不支持，固定 1 张 | ✅ 1-4 | ❌ 固定 1 | - |
| seed（种子） | ❌ | ❌ | ✅ 可选（0=随机） | ✅ 可选 |
| strength（强度） | ❌ 无此参数，节点将其转成提示词指令 | 同左 | - | - |
| 时长 | - | - | seconds "4"~"12"（节点用 帧数/帧率 换算） | num_frames（8n+1） |
| frame_rate | - | - | ❌ API 无此参数 | ✅ 传给 API |
| 图片参考 | - | - | ✅ reference 模式 images[] 最多 5 张（参考视频生成节点 image_1~5；<Picture N> 指代） | ⚠️ extra_body.image 多图（参考视频生成节点兼容，无 <Picture N>） |
| 音频参考 | - | - | ✅ reference 模式 audios[] 最多 3 段（本地路径/URL/Data URI，<Audio N> 指代） | ❌ 不支持 |
| 关键帧（首尾帧） | - | - | ✅ keyframe 模式 first_frame/last_frame（关键帧生视频节点） | ⚠️ 多图 img2video（无独立尾帧参数） |
| reasoning_effort（思考等级） | 仅文本模型 | - | - | - |

> 思考等级：文本节点（场景切分/总导演/资产提取/分镜提示词/剧本生成/LLM 对话）
> 均带 reasoning_effort 下拉（auto/none/low/medium/high/max；auto=不传参数跟随模型
> 默认）；2.5-flash 5 档，3.0-flash 7 档（本套件暴露 5 档），2.0 旧模型不生效。
| quality | 即 size 档位 | 1K/2K | ❌ 固定 720P，无此参数 | 映射 WxH 像素 |
| max_wait | 客户端轮询超时，非 API 参数 | 同左 | 同左 | 同左 |

> 结论：新 2.5 系列图像模型**支持 ratio 宽高比**（8 种，配合 1K-4K 档位），
> 图像/视频节点的 aspect_ratio 下拉均可直接使用；新模型不再支持 n/strength/
> seed（图）/frame_rate（视）等参数，节点中保留这些输入框是为了兼容旧模型和
> 习惯；使用新模型时它们不生效（已在各 widget 的 tooltip 中注明）。视频 2.5 支
> 持 seed，可直接传入做可复现实验。

---

## 节点配置说明

### 🎬 Agnes 场景切分 (AgnesSceneSplitter)

**功能：** 将小说章节拆分为 5 秒/片的场景段落

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 小说章节文本，建议 3000-8000 字 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

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
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

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
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

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
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| style | COMBO | cinematic | 图像风格：cinematic/anime/realistic/watercolor/oil_painting |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |
| characters_json | STRING | "" | 角色信息 JSON（可选） |
| locations_json | STRING | "" | 场景信息 JSON（可选） |

**输出：**
- detailed_prompt: 英文提示词

---

### 🎨 Agnes 图像生成 (AgnesImageGen)

**功能：** 根据提示词生成场景图像

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 英文图像描述 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| width | INT | 1920 | 图像宽度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效 |
| height | INT | 1080 | 图像高度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效 |
| quality | COMBO | 1K | 画质档位：1K/2K/3K/4K（新图像模型 agnes-image-2.5-flash 按档位出图，2K 性价比最高） |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型，可选 2.5-flash / 2.1-flash / 2.0-flash（选旧模型时 width/height 按像素生效） |
| aspect_ratio | COMBO | 16:9 | 宽高比（与视频节点一致）：新接口与 quality 档位组合出图，如 16:9 + 2K = 2624×1472；支持 1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9；旧接口不生效 |

**输出（含输出描述）：**
- image: 图像张量（连接视频生成节点或 SaveImage）
- url: 图片 URL（保存的文件路径/下载 URL）

---

### 🎬 Agnes 视频生成 (AgnesVideoGen)

**功能：** 文生视频 / 单图参考生视频（接一张 image 走 2.5-flash reference 模式）

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

> 多张图片/音频参考请用「🎞️ Agnes 参考视频生成」节点；首尾帧请用「🎬 Agnes 关键帧生视频」节点。

---

### 🎬 Agnes 关键帧生视频 (AgnesNovelImageToVideo)

**功能：** 关键帧生视频（原「Agnes Novel 图生视频」）：首帧必接、尾帧可选；
2.5-flash 走 keyframe 首尾帧模式，接尾帧=首尾帧过渡（image→image 运动）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| image | IMAGE | 必接 | 关键帧·首帧（first_frame） |
| prompt | STRING | "" | 视频描述（可选） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（2.5-flash keyframe 模式 / 旧 v2.0 帧数模式） |
| quality | COMBO | 1K | 仅旧接口生效；2.5-flash 固定 720P |
| aspect_ratio | COMBO | 16:9 | 宽高比 |
| num_frames / frame_rate | INT | 121 / 24 | 旧接口帧数/帧率；新接口按 帧数/帧率 换算 4-12 秒 |
| seed | INT | 0 | 随机种子（0=每次随机） |
| max_wait_seconds | INT | 600 | 轮询超时 |
| end_frame_image | IMAGE | - | 关键帧·尾帧（可选，last_frame；不接=仅按首帧生成） |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 output/agnes_videos/，输出类型随环境为 VIDEO/VHS/路径）
- resolution: 视频目标尺寸（WxH）

> 多张参考图/音频参考请用「🎞️ Agnes 参考视频生成」节点。

---

### 🎞️ Agnes 参考视频生成 (AgnesVideoReference)

**功能：** 参考素材生视频（2.5-flash reference 模式）：最多 5 张参考图
（image_1~5，提示词用 `<Picture N>` 指代）+ 最多 3 段参考音频
（audio_1~3，提示词用 `<Audio N>` 指代；音频为本地文件路径或公开 URL，
本地文件自动转 Base64 Data URI，单段 <15MB）。至少提供一种媒体参考。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 视频描述；`<Picture 1>~5` / `<Audio 1>~3` 指代参考素材 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 2.5-flash（支持图片+音频参考）/ 旧 v2.0（仅多图，音频忽略） |
| num_frames / frame_rate | INT | 121 / 24 | 新接口换算 4-12 秒；旧接口直接传 API |
| quality | COMBO | 1K | 仅旧接口生效；2.5-flash 固定 720P |
| aspect_ratio | COMBO | 16:9 | 宽高比 |
| seed | INT | 0 | 随机种子（0=每次随机） |
| max_wait_seconds | INT | 600 | 轮询超时 |
| image_1 ~ image_5 | IMAGE | - | 参考图片（1 必接或可只接音频；2.5-flash 上限 5 张） |
| audio_1 ~ audio_3 | STRING | "" | 参考音频（本地路径或公开 URL；仅 2.5-flash，上限 3 段） |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 output/agnes_videos/）
- resolution: 视频目标尺寸（WxH）

---

### 📝 Agnes 剧本生成 (AgnesScriptGenerator)

**功能：** 生成影视解说文案

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| story_outline | STRING | "" | 故事大纲 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| style | COMBO | casual | 解说风格：casual/professional/humorous/dramatic |
| target_duration | INT | 180 | 目标时长（秒） |
| temperature | FLOAT | 0.8 | 生成温度（0-1） |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

**输出：**
- script: 解说文案

---

### 📐 Agnes 三视图生成 (AgnesSubjectTurnaround)

**功能：** 生成任意主体的三视图设定表（turnaround sheet）：同一主体三个视图
从左到右并排（角色=正/侧/背全身 A-pose；物品=产品设定；场景=正立面/侧立面/
俯视图；载具=整车设定；通用=任意主体），正交视图、比例与细节一致

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| subject_type | COMBO | 角色 | 主体类型：角色/物品道具/场景/载具/通用，决定三视图提示词模板 |
| subject_desc | STRING | "" | 主体名 + 外观/材质/结构描述（越具体越一致） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | 留空自动加载 | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型 |
| quality | COMBO | 2K | 档位：1K/2K/3K/4K |
| aspect_ratio | COMBO | 21:9 | 三视图推荐宽幅 21:9 / 16:9 |
| reference_image | IMAGE | - | 可选：定妆图/已有设定图，连接后走图生图保持一致 |
| extra_prompt | STRING | "" | 可选：追加风格/质量补充词 |

**输出：**
- image: 三视图张量（可存图或作为后续视频节点参考）
- resolution: 实际分辨率
- final_prompt: 最终拼接的完整提示词

> 原「Agnes 角色三视图设定图」节点（AgnesNovelCharacterTurnaround）已升级为本
> 通用节点；角色三视图选 subject_type=角色（默认）即可，原用法不变。

### 🔗 Agnes 字符串合并 (AgnesStringMerge)

**功能：** 上下合并两个多行字符串（纯文本节点，不调用 API、无需 API Key）：
非空输入按顺序拼接，空输入自动跳过（不产生多余空行/尾随分隔符），
适合把多段章节文本、多个节点的 STRING 输出合并成一个完整字符串

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| string_1 | STRING(多行) | "" | 第一段字符串（上），可连任意 STRING 输出 |
| string_2 | STRING(多行) | "" | 第二段字符串（下），可连任意 STRING 输出 |
| separator | STRING | （一个换行） | 可选：两段之间的分隔符；留空=直接首尾相接 |

**输出：**
- result: 上下合并后的字符串

> 用法示例：场景切分的 scene_3 连 string_1、scene_4 连 string_2 →
> 输出「段3\n段4」；把 LLM 对话的两段回复合并成一整段。

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

### 图生图 503「生图队列已满」而文生图正常
- Agnes 服务端的**文生图与图生图是两条独立队列**：图生图队列（带参考图的
  重任务）容易饱和，此时文生图仍可正常出图——这是服务端排队，不是节点参数错误
- 客户端已自动按 15/30/60/120 秒退避重试（最多 5 次，累计约 3.75 分钟）；
  仍失败请等 5-10 分钟后再运行该节点
- 长链式图生图（如 50 场景 bible 工作流）逐个排队消耗图生图队列，
  可先用少量场景（test3 精简版）验证再跑全量

---

## 输出文件位置

| 类型 | 位置 |
|------|------|
| 分镜脚本 | `%USERPROFILE%\Documents\AgnesOutput\` |
| 视频文件 | `ComfyUI/output/agnes_videos/` |

---

**版本**: 1.8.1  
**更新日期**: 2026-10-19
