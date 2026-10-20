# Agnes 插件 - 节点配置指南

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
| n（张数） | ❌ 固定 1 张 | ⚠️ 曾支持 1-4，现服务端 n>1 返回 400（图像节点自动降级 1 张） | ❌ 固定 1 | - |
| seed（种子） | ❌ | ❌ | ✅ 可选（0=随机） | ✅ 可选 |
| strength（强度） | ❌ 无此参数，节点将其转成提示词指令 | 同左 | - | - |
| 时长 | - | - | seconds "4"~"12"（节点用 帧数/帧率 换算） | num_frames（8n+1） |
| frame_rate | - | - | ❌ API 无此参数 | ✅ 传给 API |
| 图片参考 | - | - | ✅ reference 模式 images[] 最多 5 张（参考视频生成节点 image_1~5；<Picture N> 指代） | ⚠️ extra_body.image 多图（参考视频生成节点兼容，无 <Picture N>） |
| 音频参考 | - | - | ✅ reference 模式 audios[] 最多 3 段（本地路径/URL/Data URI，<Audio N> 指代） | ❌ 不支持 |
| 关键帧（首尾帧） | - | - | ✅ keyframe 模式 first_frame/last_frame（关键帧生视频节点） | ⚠️ 多图 img2video（无独立尾帧参数） |
| reasoning_effort（思考等级） | 仅文本模型 | - | - | - |

> 思考等级：走 LLM 的节点（场景切分/总导演/资产提取/分镜提示词/剧本生成/LLM 对话/
> 资产提示词生成/三视图提示词生成/图像反推提示词）均带 reasoning_effort 下拉
> （auto/none/low/medium/high/max；auto=不传参数跟随模型默认）；
> 2.5-flash 5 档，3.0-flash 7 档（本套件暴露 5 档），2.0 旧模型不生效。
| quality | 即 size 档位 | 1K/2K | ❌ 固定 720P，无此参数 | 映射 WxH 像素 |
| max_wait | 客户端轮询超时，非 API 参数 | 同左 | 同左 | 同左 |

> 结论：新 2.5 系列图像模型**支持 ratio 宽高比**（8 种，配合 1K-4K 档位），
> 图像/视频节点的 aspect_ratio 下拉均可直接使用；新模型不再支持 n/strength/
> seed（图）/frame_rate（视）等参数，节点中保留这些输入框是为了兼容旧模型和
> 习惯；使用新模型时它们不生效（已在各 widget 的 tooltip 中注明）。视频 2.5 支
> 持 seed，可直接传入做可复现实验。

---

## 节点配置说明

### 📥 Agnes 文本输入 (AgnesNovelTextSource)

**功能：** Agnes 专属字符串输入接口（纯输入节点，不调用 API、无需 API Key）：
手动输入/粘贴小说章节内容、故事想法、解说草稿等文本，
「文本」输出口直连任意 Agnes 文本类节点，替代灰色的通用 PrimitiveNode

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| text | STRING(多行) | "" | 小说章节 / 故事想法 / 解说草稿 / 角色场景描述等任意文本 |

**输出：**
- text: 输入的文本原样输出（未输入时为空字符串）

> 用法示例：
> 文本输入（章节内容）→ Agnes 场景切分（整条管线起点）；
> 文本输入（故事想法）→ Agnes LLM 对话（想法扩写成故事大纲）→ Agnes 剧本生成（解说文案）；
> 文本输入（解说草稿）→ Agnes LLM 对话（润色/改写/口语化）。

---

### 🪄 Agnes 风格选择 (AgnesStyleSelector)

**功能：** 漫剧/短视频全局风格定制（纯本地组合，不调用 API、无需 API Key）：
两个风格轴 + 可选自由补充，组合成「风格规范」输出，供后续所有资产生成（图像/视频/分镜提示词）统一遵循

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| visual_style | COMBO | 二次元2D | 视觉风格（画面长什么样，用于生成图片/视频）：国风3D/二次元2D/国漫手绘/90年代/真人古风/现代都市/像素复古/剪纸皮影/水墨仙侠/Q版萌系 |
| director_style | COMBO | 家庭温馨 | 导演风格（故事怎么讲，叙事基调与节奏）：青春成长/家庭温馨/历史史诗/恐怖异灵/喜剧搞笑/科幻未来/都市末世/都市异能/悬疑解谜/逆袭爽文 |
| extra（可选） | STRING(多行) | "" | 追加风格要求，如「暖色调、大景深」 |

**输出（4 路）：**
- style_block: 风格说明块（视觉+导演+补充，可直接注入提示词或喂 LLM）
- visual_style_out: 视觉风格名
- director_style_out: 导演风格名
- style_json: 机器可读 JSON `{"visual":"...","director":"...","extra":"..."}`

> 示例组合：橘猫团团故事 = 二次元2D × 家庭温馨（+「暖色调」）；
> 都市黑熊悬疑 = 现代都市 × 悬疑解谜；
> 古风仙侠 = 水墨仙侠 × 历史史诗。
> 说明：当前节点独立输出风格规范，后续资产节点（生图/生视频）自动接入风格为下一步工作。

---

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
- log_text: 处理日志（成功=段落数+响应元数据 finish_reason/token 消耗；空响应=⚠️警示；失败=异常+堆栈）
- scene_1 ~ scene_50: 最多 50 个场景片段
- chapter_text_out: 原文本（透传）
- api_key_out / base_url_out / model_out: 配置透传

> 输入为空（chapter_text 留空/上游未连）时直接跳过、不调 API：log_text 显示「[跳过] 输入为空…」，各槽为空。

---

### 🎬 Agnes 总导演 (AgnesDirectorMaster)

**功能：** 将故事内容（**小说章节或 漫剧剧本 均可**）生成为完整编号分镜脚本（5 秒/镜）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 故事内容：小说章节原文（建议 3000-8000 字），或「Agnes 剧本生成」（漫剧剧本）的输出 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

**输出：**
- log_text: 处理日志（成功=分镜数+响应元数据 finish_reason/token 消耗；空响应=⚠️警示；失败=异常+堆栈）
- scene_1 ~ scene_50: 分镜脚本
- chapter_text_out / api_key_out / base_url_out / model_out: 透传
- shot_count: 分镜总数（统计实际解析出的分镜数；超过 50 时标注「N（仅显示前 50 个）」；失败/无 Key/输入为空时为空）

> 输入为空（chapter_text 留空/上游未连）时直接跳过、不调 API：log_text 显示「[跳过] 输入为空…」，各槽为空。

> 两种接法：
> - 小说线：章节原文 → 总导演（章→镜一步到位）
> - 漫剧线：大纲 → Agnes 剧本生成（漫剧，场级 5–15 秒）→ 总导演（场→镜精化，每场拆 2–4 镜）→ 分镜提示词生成 → 生图/生视频
> - 注意：漫剧线 快节奏（5–8 秒/场）× 180 秒 ≈ 30 场 → 60+ 镜，会超出 scene_50 上限；建议漫剧线用 中速/慢热 或缩短 target_duration

---

### 📋 Agnes 资产提取 (AgnesAssetExtractor)

**功能：** 将故事内容（**小说章节或 漫剧剧本 均可**）提取为角色、场景、道具等 5 路资产 JSON

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 故事内容：小说章节原文（建议 3000-8000 字），或「Agnes 剧本生成」（漫剧剧本）的输出 |
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
- log_text: 处理日志（成功=各路统计+响应元数据；空响应=⚠️警示；JSON 解析失败=提示；异常=堆栈）

> 空正文排查：log_text 显示 "⚠️ 空响应"（5 个 JSON 槽全空）：① reasoning_effort → none/low ② 换 agnes-2.5-flash ③ 原样重跑一次（排除服务器偶发）。

> 输入为空（chapter_text 留空/上游未连）时直接跳过、不调 API：log_text 显示「[跳过] 输入为空…」，各槽为空。

> 两种接法：
> - 小说线：章节原文 → 资产提取（章节里什么都有，服装/天气字段较全）
> - 漫剧线：Agnes 剧本生成（漫剧）→ 资产提取（资产=该集要拍的，更准更省；但漫剧剧本格式里服装/天气字段偏弱，这两路 JSON 可能偏稀——没有就不生成，属正常）

---

### 🎨 Agnes 分镜提示词生成 (AgnesScenePromptGenerator)

**功能：** 将分镜脚本转换为英文生图提示词

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| scene_text | STRING | "" | 分镜文本（从场景切分或总导演获取） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| style | COMBO | cinematic | 图像风格：cinematic/anime/realistic/watercolor/oil_painting |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |
| characters_json | STRING | "" | 角色信息 JSON（可选） |
| locations_json | STRING | "" | 场景信息 JSON（可选） |

**输出：**
- detailed_prompt: 英文提示词
- log_text: 处理日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常+堆栈）

> 输入为空（scene_text 留空/上游未连）时直接跳过、不调 API：日志显示「[跳过] 分镜文本为空…」，detailed_prompt 为跳过提示。

---

### 🎨 Agnes 图像生成 (AgnesImageGen)

**功能：** 根据提示词生成场景图像

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 英文图像描述 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型，可选 2.5-flash / 2.1-flash / 2.0-flash（选旧模型时 width/height 按像素生效） |
| width | INT | 1920 | 图像宽度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效 |
| height | INT | 1080 | 图像高度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效 |
| quality | COMBO | 1K | 画质档位：1K/2K/3K/4K（新图像模型 agnes-image-2.5-flash 按档位出图，2K 性价比最高） |
| aspect_ratio | COMBO | 16:9 | 宽高比（与视频节点一致）：新接口与 quality 档位组合出图，如 16:9 + 2K = 2624×1472；支持 1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9；旧接口不生效 |
| n | INT | 1 | 单次请求生成张数 1-4：当前服务端对所有图像模型限单张（n>1 自动降级 1 张并打印提示），API 解锁后直接生效；多资产请多节点实例各出 1 张 |

**输出（含输出描述）：**
- image: 图像张量（n=1 单张；n>1 批量，连接 SaveImage 或视频/三视图节点）
- url: 图片 URL（保存的文件路径/下载 URL）
- resolution: 实际输出分辨率（WxH）

> 原「Agnes 文生图」节点（AgnesNovelTextToImage）的多张生成功能（n 1-4）已并入本节点，
> 文生图节点已删除；单张出图直接用本节点（n=1）

> 提示词为空（prompt 留空/上游未连）时直接跳过、不调 API：输出黑图占位 + 日志「[跳过] 提示词为空…」，避免空请求被误判为「空响应」。

---

### 🎞️ Agnes 文生视频 (AgnesNovelTextToVideo)

**功能：** 文生视频：按提示词直接生成视频（替代原「Agnes 视频生成」AgnesVideoGen，该节点已删除；
图参考/首尾帧请改用「Agnes 关键帧生视频」或「Agnes 参考视频生成」节点）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 视频描述（建议英文提示词） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型，可选 2.5-flash（4-12s/720P）/ agnes-video-v2.0（帧数模式） |
| quality | COMBO | 1K | 画质档位：仅旧接口 1K/2K 生效（映射 WxH 像素）；新接口 2.5-flash 固定 720P |
| aspect_ratio | COMBO | 16:9 | 宽高比（支持 12 种；新接口不支持的比例自动就近映射） |
| num_frames | INT | 121 | 帧数（旧接口必须 8n+1，121≈5s@24fps）；新接口按 帧数/帧率 换算 4-12 秒时长 |
| frame_rate | INT | 24 | 帧率：旧接口传给 API；新接口仅用于换算时长 |
| seed | INT | 0 | 随机种子（0=每次随机，固定值可复现结果） |
| max_wait_seconds | INT | 600 | 轮询超时 |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 ComfyUI output/agnes_videos/；输出类型随环境为 VIDEO/VHS_VIDEOINFO/路径字符串），可连接 SaveVideo 预览
- resolution: 视频目标尺寸（WxH）；新接口 2.5-flash 固定 720P，实际像素随 aspect_ratio 变化

> 原「Agnes 视频生成」节点（AgnesVideoGen，含 image 参考输入）已删除：
> 文生视频用本节点；单图首帧/首尾帧请用「🎬 Agnes 关键帧生视频」节点；
> 多张图片/音频参考请用「🎞️ Agnes 参考视频生成」节点。

---

### 🎬 Agnes 关键帧生视频 (AgnesNovelImageToVideo)

**功能：** 关键帧生视频（原「Agnes 图生视频」）：首帧必接、尾帧可选；
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

### 📝 Agnes 解说剧本生成 (AgnesScriptGenerator)

**功能：** 生成影视解说文案（口播稿/配音轨，对观众的叙述腔）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| story_outline | STRING | "" | 故事大纲 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| style | COMBO | casual | 解说风格：casual/professional/humorous/dramatic |
| target_duration | INT | 180 | 目标时长（秒） |
| temperature | FLOAT | 0.8 | 生成温度（0-1） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

**输出：**
- script: 解说文案
- log_text: 响应日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常+堆栈）

> 空正文排查：log_text 显示 "⚠️ 空响应"（script 槽为空）：① reasoning_effort → none/low ② 换 agnes-2.5-flash ③ 原样重跑一次。

> 输入为空（story_outline 留空/上游未连）时直接跳过、不调 API：日志显示「[跳过] 故事大纲为空…」，script 为跳过提示。

---

### 🎭 Agnes 剧本生成 (AgnesScreenplayGenerator)

**功能：** 生成**漫剧短视频分场剧本**（与「解说剧本生成」的区分：本节点产"画面+对白+氛围"的分场结构，不是对观众的口播解说腔）：
开头一行「核心钩子」+ 逐场四行结构（场景行/画面/对白/氛围），画面描述具象可视、可直接转镜头。
剧本类型按**三维**定制：题材标签（讲什么）× 情绪基调（观众什么感受）× 节奏（多快），三个参数自由组合

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| story_outline | STRING(多行) | "" | 故事大纲或章节摘要 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型 |
| tag | STRING | 逆袭爽文 | 题材标签（讲什么），可**手输**或**连线**：逆袭爽文/甜宠CP/悬疑解谜/搞笑沙雕/热血动作/治愈日常/虐心催泪 + 风格选择对齐 8 项（青春成长/家庭温馨/历史史诗/恐怖异灵/喜剧搞笑/科幻未来/都市末世/都市异能）；留空=默认逆袭爽文，未知名自动按通用描述兜底不报错 |
| emotion | COMBO | 爽 | 情绪基调：爽/暖/爆笑/热血/紧张/泪 |
| rhythm | COMBO | 快节奏 | 节奏：快节奏（钩子每 1–2 场）/ 中速（每 3–4 场）/ 慢热（只留 3 个转折点钩子）；同时决定每场秒数（5–8 / 8–12 / 12–15） |
| target_duration | INT | 180 | 目标总时长（秒），场次按节奏估算（快≈6s/场、中≈9s/场、慢≈13s/场） |
| temperature | FLOAT | 0.8 | 生成温度（0-1） |
| reasoning_effort | COMBO | auto | 思考等级（2.5/3.0 文本模型）：auto/none/low/medium/high/max |
| characters（可选） | STRING(多行) | "" | 角色列表：每行「名字：一句人设」，让对白/动作保持角色一致 |

**输出：**
- script: 漫剧剧本（核心钩子 + 分场四行结构：场景行/画面/对白/氛围）
- log_text: 响应日志（成功=三维参数/场次估算/响应元数据 finish_reason+token 消耗/耗时/原始响应摘录；空响应=⚠️ 警示+排查建议；失败=异常类型/完整堆栈/请求参数/请求地址/解决建议，覆盖 API Key 缺失、网络超时、HTTP 错误、响应格式异常全部报错情况）

> 三维组合示例（橘猫团团故事）：
> - 治愈日常 × 暖 × 慢热 → 市井烟火慢镜头版
> - 悬疑解谜 × 紧张 × 快节奏 → 黑熊追击快切版
> - 治愈日常 × 泪 × 中速 → 结尾"熊掌印"反转催泪版
> 管线接法：文本输入（章节）→ 剧本生成（漫剧）→ 场景切分 → 分镜提示词生成 → 图像生成 → 关键帧生视频；
> 或把输出接 SaveText 存档，人工修改对白后再进管线。
> 风格联动：Agnes 风格选择（导演风格，如「科幻未来」）→ 剧本生成（**tag 输入，直接连线**，覆盖手输值）→ 剧本按该题材方向创作；视觉风格用于后续资产生成。
> 排错：执行报错看节点「响应日志」输出（覆盖 API Key/网络/HTTP/响应格式全部情况）；若日志显示 "Failed to validate prompt / Return type mismatch"（校验失败、节点没跑），多为旧存档问题——删掉该节点重新拖入、把「风格选择.导演风格」连到 **tag** 输入即可。
> 空响应：若日志显示 "⚠️ 空响应（API 返回 200 但正文为空）"，多为思考型模型预算耗尽（3.0-flash medium + 场次多，思考链占满输出上限）——降思考等级（none/low）、换 agnes-2.5-flash 或减场次后重跑；日志里的 finish_reason 与 token 消耗可佐证。
> 输入为空（story_outline 留空/上游未连）时直接跳过、不调 API：日志显示「[跳过] 故事大纲为空…」，script 为跳过提示。

---

### 📐 Agnes 三视图生成 (AgnesSubjectTurnaround)

**功能：** 纯出图节点，**不再内置任何提示词模板**——直接用 subject_desc 输入的
**完整三视图提示词**出图。提示词推荐由 `Agnes 三视图提示词生成` 节点输出
（或手工编写/修改后填入），出什么图完全由这段提示词决定

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| subject_desc | STRING(多行) | "" | 完整三视图提示词：推荐连 Agnes 三视图提示词生成 的「三视图提示词」输出，或手动粘贴/手工修改后的提示词 |
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
- final_prompt: 实际使用的完整提示词（subject_desc + extra_prompt），可复制复用或微调

> 接法：`Agnes 三视图提示词生成.三视图提示词` → `三视图生成.subject_desc`
> （21:9 宽幅避免三视图被裁切；想与已有资产一致就 reference_image 接定妆图）

---

### ✍️ Agnes 三视图提示词生成 (AgnesTurnaroundPromptGenerator)

**功能：** 把原始主体描述/提示词（资产提示词生成节点输出，或手写的中英文描述）
转成一条**完整可见的三视图英文提示词**（内置分栏布局指令「左侧 1/3 区域超大特写 +
右侧 2/3 区域整齐排布三视图」+ 虚幻引擎渲染风格/PBR材质/柔和漫射光 +
纯主体规格「纯白背景、干净极简、无阴影」+ 8K 质量尾词），并**自动去掉原文中与三视图矛盾的单视图
字样（single front view / facing the camera 等）**。输出可复制到
三视图生成节点的 subject_desc 手工修改优化后再出图

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| subject_prompt | STRING(多行) | "" | 原始主体描述/提示词：连 Agnes 资产提示词生成 的「英文资产生成提示词」输出，或手动粘贴任意中英文描述 |
| subject_type | COMBO | 角色 | 角色/物品道具/服装/场景/载具/通用（决定分栏布局指令：角色=面部特写+全身正侧背 / 物品=细节特写+三视图 / 服装=细节特写+正侧背 / 场景=局部特写+正立面/侧立面/俯视 / 载具=局部特写+整车三视图 / 通用） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key，留空自动加载全局 |
| model | COMBO | agnes-2.5-flash | 文本生成模型 |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型） |

**输出：**
- 三视图提示词: 完整三视图英文提示词（主体全部细节保留 + 分栏布局「左 1/3 特写 + 右 2/3 三视图」+ 虚幻引擎渲染风格/PBR/柔和漫射光 + 纯白背景干净极简无阴影 + 8K 质量尾词），可连 三视图生成 或复制后手工修改
- 处理日志: 成功=提示词摘要+响应元数据；空响应=⚠️警示；失败=异常+堆栈

> 空正文排查：处理日志显示 "⚠️ 空响应"（三视图提示词槽为空）：① reasoning_effort → none/low ② 换 agnes-2.5-flash ③ 原样重跑一次。

> 完整资产三视图链路：
> `资产提取 → 文本拆分(第N条) → 资产提示词生成 → 三视图提示词生成 → [查看/手工改三视图提示词] → 三视图生成`

### 🔗 Agnes 字符串合并 (AgnesStringMerge)

**功能：** 上/中/下合并三个多行字符串（纯文本节点，不调用 API、无需 API Key）：
非空段落按 上→中→下 顺序拼接，空段落自动跳过（不产生多余空行/尾随分隔符），
适合把多段章节文本、多个节点的 STRING 输出合并成一个完整字符串；
「中段」专为**人工衔接语**设计：两段提示词之间手输一句过渡/连接描述（也可连 LLM 对话等节点输出）

面板控件自上而下依次为：**第一段字符串（上）→ 第二段字符串（中）→ 第三段字符串（下）→ 分隔符**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| string_1 | STRING(多行) | "" | **第一段（上）**，可连任意 STRING 输出 |
| string_3 | STRING(多行) | "" | **第二段（中，人工衔接语）**：手输过渡语或连 LLM 对话/文本节点输出；留空=上、下直接合并 |
| string_2 | STRING(多行) | "" | **第三段（下）**，可连任意 STRING 输出 |
| separator | STRING | （一个换行） | 可选：段落之间的分隔符；留空=直接首尾相接。空段落被跳过时不产生尾随分隔符 |

> 注：合并顺序固定为 上→中→下（按槽位语义，与面板位置一致）。
> 旧版（两槽/顺序为上、下、分隔符）保存的工作流加载时 widgets_values 按位置映射，
> 旧「下」段值会落到「中」、旧分隔符值会落到「下」——旧文件请重新填一遍。

**输出：**
- result: 上/中/下合并后的字符串

> 用法示例：
> ① 场景切分的 scene_3 连 string_1、scene_4 连 string_2 → 输出「段3\n段4」
> ② 提示词人工衔接：分镜提示词 A 连 string_1（上）、提示词 B 连 string_2（下）、
> string_3 手输「随后镜头缓缓推进至……」→ 输出「A\n过渡语\nB」（段落间按 separator 分隔）
> ③ 中段也可以连线：LLM 对话节点的输出（如让模型写一句过渡语）→ string_3

---

### ✂️ Agnes 文本拆分 (AgnesTextSplitter)

**功能：** 把一整段文本（资产 JSON 列表 / LLM 输出的分块文本 / 编号列表 / 多段文本）
拆成**最多 20 路独立字符串**（纯文本节点，不调用 API、无需 API Key），
实现「一个角色/道具/场景 = 一路输出 = 一张图」的批量资产出图

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| text | STRING(多行) | "" | 要拆分的完整文本；可连资产提取的任意 JSON 输出 / LLM 对话回复 / 手动粘贴 |
| mode | COMBO | JSON 数组 | 拆分模式（见下表） |

**拆分模式：**

| 模式 | 适用输入 | 拆分规则 |
|------|----------|----------|
| JSON 数组 | 资产提取直出的 JSON（`[{"name":"苏尘",...}, ...]` 或 `{"characters":[...]}`） | 每个 JSON 元素/对象输出一路（带缩进美化） |
| 【】括号块 | LLM 输出的定妆文（「【苏尘】黑发男子…【柳如烟】白衣…」） | 每个【名】起头、到下一个【前 |
| 编号列表 | 「1. … 2、… 一、… (3) …」格式 | 每个编号行一条 |
| 空行段落 | 空行分隔的多段文本 | 每个段落一条 |

**输出：**
- 第 1 条 ~ 第 20 条: 拆分出的独立文本（不足 20 条的槽位为空）
- 条数: 实际条目总数（超过 20 条时显示「N（仅显示前 20 条）」）
- 原文透传: 原始输入（并联其他节点或存档）

> **资产线完整接法（角色/场景/道具/服装 三视图）：**
> ① `Agnes 资产提取.角色JSON` →（可选）`LLM 对话`（提示词写死：把 JSON 逐条扩写成
> 「【名】+定妆描述」格式，一次全出）→ `Agnes 文本拆分`（mode=【】括号块 或 JSON 数组）
> ② 拆分 `第 N 条` → `Agnes 资产提示词生成`（subject_type 选 角色/道具/场景/服装，
> 输出英文资产提示词）→ `Agnes 三视图提示词生成`（同 subject_type，输出完整三视图提示词）
> ③ `三视图提示词`（可查看/手工修改）→ `Agnes 三视图生成.subject_desc`（21:9 宽幅；
> 要系列一致就 reference_image 接一张已出的定妆图）
> 场景/道具/服装 JSON 走同一条链，只换两节点的 subject_type
> 资产超过 20 个时看「条数」输出提示，手动分批或让 LLM 合并小项

---

### 💬 Agnes LLM 对话 (AgnesNovelLLMChat)

**功能：** 与 Agnes 对话模型自由对话（通用 LLM 文本节点：扩写/改写/批量转换/任意指令），
可选系统提示词、Thinking 开关与思考等级。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING(多行) | "" | 用户消息 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL |
| api_key | STRING | sk-你的Key | Agnes AI API Key，留空自动加载全局 |
| model | COMBO | agnes-2.5-flash | 对话模型（2.5-flash 默认 / 3.0-flash Agent） |
| temperature | FLOAT | 0.7 | 采样温度 |
| system_prompt（可选） | STRING(多行) | "" | 系统提示词（角色/行为设定） |
| enable_thinking（可选） | BOOLEAN | 关 | Thinking 模式开关（消耗更多 token） |
| reasoning_effort（可选） | COMBO | auto | 思考强度：auto/none/low/medium/high/max |

**输出：**
- AI回复: 完整回复文本
- 响应日志: 成功=字数+响应元数据（finish_reason/token 消耗）；空响应=⚠️警示；失败=异常+堆栈

> 控件显示 "NaN" 排查（适用于带数字控件的节点）：
> 旧版工作流里该节点保存的 widgets_values 位置错位，数字控件槽载到了相邻槽的值
> （如 reasoning_effort 的 "auto"），显示成 NaN。处理：点一下该控件重新输入数值
> 再保存工作流即可。本版本已移除 max_tokens 控件，输出长度上限由模型自动决定。

---

### 🖌️ Agnes 资产提示词生成 (AgnesAssetPromptGenerator)

**功能：** 把单条资产 JSON 转成**可直接生图的英文提示词**（内置 art-director 模板，
按主体类型换构图指令 + 风格尾词 + quality 词，免去手写 LLM 指令）。
**纯主体 + 单一正视图**：画面只含主体本身（纯白底，从头到尾完整可见），只出正面视图（不出侧面/背面/三视图），不含场景背景、打光氛围与镜头描述。
输出接 图像生成 / 三视图生成(subject_desc)，完成资产线的最后一步。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| asset_json | STRING(多行) | "" | 单条资产 JSON：连 Agnes 文本拆分任一输出槽，或粘贴单个资产 JSON 对象 |
| subject_type | COMBO | 角色 | 角色/物品道具/服装/场景/载具/通用（决定构图指令，与三视图一致 + 服装） |
| style | COMBO | cinematic | 生图风格尾词：cinematic/anime/realistic/watercolor/oil_painting |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key，留空自动加载全局 |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型） |

**输出：**
- 英文资产生成提示词: 保留 JSON 全部描述字段（专名拼音化）+ 构图指令 + 风格/质量尾词，直接喂生图
- 处理日志: 成功=提示词摘要预览+响应元数据；失败=错误原因

> 空正文排查：处理日志显示 "⚠️ 空响应"（API 200 但正文 0 字，多为思考模型预算耗尽）：
> ① reasoning_effort → none/low ② 换 agnes-2.5-flash ③ 原样重跑一次（排除服务器偶发）。

> **资产线完整接法（角色/道具/场景/服装 → 设定图）：**
> ① `Agnes 资产提取.角色JSON` → `Agnes 文本拆分`（JSON 数组模式）
> ② 拆分 `第 N 条` → `Agnes 资产提示词生成`（subject_type=角色，style 自选）
> ③ `英文资产生成提示词` → `Agnes 图像生成`（n=1，或 三视图提示词生成 → 三视图生成 subject_desc，
>    想系列一致再 reference_image 接一张已出图）
> 场景/道具/服装走同一条链，换 subject_type 即可
> 批量省调用：也可用 LLM 对话一次把整份 JSON 转成【名】英文提示词，
> 再接 文本拆分(【】括号块模式) 扇出（少 19 次 LLM 调用）

---

## 推荐配置

### 快速测试
- 按下方「完整流程」自行搭建最小链路
- 只配置 API Key
- 输入一段小说文本

### 完整流程
1. **场景切分** → 获取 scene_1
2. **资产提取** → 获取 characters_json, locations_json
3. **提示词生成** → 连接 scene_1 + characters_json + locations_json
4. **图像生成** → 生成场景图像
5. **文生视频** → 按提示词生成视频（图参考请用「Agnes 关键帧生视频」/「Agnes 参考视频生成」节点）
6. **剧本生成** → 独立流程，生成解说文案

---

## 成本估算

| 操作 | 单价估算 | 单集成本 (20场景) |
|------|----------|-------------------|
| LLM 调用 | ~0.001 USD | ~0.10 USD |
| 图像生成 | ~0.01 USD | ~0.20 USD |
| 文生视频 | ~0.10 USD | ~2.00 USD |
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

**版本**: 1.12.0  
**更新日期**: 2026-10-19
