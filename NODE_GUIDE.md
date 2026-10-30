# Agnes 插件 - 节点配置指南

## 快速开始

### 1. 获取 API Key
访问 https://platform.agnes-ai.com 注册并获取 API Key

### 2. 安装插件
```powershell
Expand-Archive -Path "ComfyUI-Agnes-Flash-Suite.zip" -DestinationPath "你的ComfyUI路径\ComfyUI\custom_nodes\" -Force
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
| 尺寸 | size 档位 1K/2K/3K/4K | width/height(WxH) | 固定 720P（API 无 size 参数；节点带 resolution 固定 720P 展示项） | width/height(WxH)（节点固定 1K 档位映射） |
| ratio（宽高比） | ✅ 1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9（默认 1:1），与档位组合决定像素，节点已提供 aspect_ratio 下拉 | ❌ 按 WxH 像素表达 | ✅ 16:9/9:16（可选，缺省服务端自动处理；16:9=1280×720，9:16=720×1280），节点下拉保留 12 种、不支持的比例自动就近映射 | ✅ 映射 WxH 像素 |
| n（张数） | ❌ 固定 1 张 | ⚠️ 曾支持 1-4，现服务端 n>1 返回 400（图像节点自动降级 1 张） | ❌ 固定 1 | - |
| seed（种子） | ❌ | ❌ | ✅ 可选（0=随机） | ✅ 可选 |
| strength（强度） | ❌ 无此参数，节点将其转成提示词指令 | 同左 | - | - |
| 时长 | - | - | seconds "4"~"12"（节点 seconds 下拉直控） | num_frames（8n+1） |
| frame_rate | - | - | ❌ API 无此参数（节点已移除帧率输入） | ✅ 传给 API |
| 图片参考 | - | - | ✅ reference 模式 images[] 最多 5 张（参考视频生成节点 image_1~5；<Picture N> 指代） | ⚠️ extra_body.image 多图（参考视频生成节点兼容，无 <Picture N>） |
| 音频参考 | - | - | ✅ reference 模式 audios[] 最多 3 段（本地路径/URL/Data URI，<Audio N> 指代） | ❌ 不支持 |
| 关键帧（首尾帧） | - | - | ✅ keyframe 模式 first_frame/last_frame（关键帧生视频节点） | ⚠️ 多图 img2video（无独立尾帧参数） |
| reasoning_effort（思考等级） | 仅文本模型 | - | - | - |
| quality（画质档位） | 即 size 档位（图像节点保留档位下拉） | 1K/2K | ❌ 无此参数（节点带 resolution 固定 720P 展示项） | 节点已移除档位下拉（固定 1K 映射 WxH） |
| max_wait | 客户端轮询超时，非 API 参数 | 同左 | 同左 | 同左 |

> 思考等级：走 LLM 的节点（场景切分/总导演/资产提取/分镜提示词/分镜提示词批量/剧本生成/LLM 对话/
> 资产提示词生成/资产提示词批量生成/三视图提示词生成/三视图提示词批量生成/图像反推提示词）均带 reasoning_effort 下拉
> （auto/none/low/medium/high/max；auto=不传参数跟随模型默认）；
> 2.5-flash 5 档，3.0-flash 7 档（本套件暴露 5 档），2.0 旧模型不生效。

> 结论：新 2.5 系列图像模型**支持 ratio 宽高比**（8 种，配合 1K-4K 档位），
> 图像/视频节点的 aspect_ratio 下拉均可直接使用；新模型不再支持 n/strength/
> seed（图）等参数，节点中保留这些输入框是为了兼容旧模型和习惯；使用新模型时
> 它们不生效（已在各 widget 的 tooltip 中注明）。视频 2.5 支持 seed，可直接传入
> 做可复现实验；视频时长直接由 seconds（4-12 秒）控制。
> 视频节点**固定 720P**（API 无 size 参数），节点带 resolution 展示项（仅 720P 一项）；
> 模型下拉只保留 Agnes Video 2.5-flash，帧数/帧率输入已移除。旧工作流视频节点
> 实例由 agnes-migrate.js 自动重映射（历史 1K/2K 档位槽丢弃 → 帧数/帧率推导
> 秒数、模型/分辨率槽回填），无需手动改图。

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

**功能：** 将故事文本（**小说章节 或 漫剧剧本**）拆分为 5 秒/片的场景段落

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| chapter_text | STRING | "" | 故事文本：小说章节全文（建议 3000-8000 字），或「Agnes 剧本生成」（漫剧剧本）/「Agnes 解说剧本生成」的输出；剧本的场景行（如"场景一：DAY 地点"）= 天然场景边界，切分比小说更规整 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（agnes-2.5-flash 默认 / agnes-3.0-flash Agent / agnes-2.0-flash 旧版） |
| reasoning_effort | COMBO | auto | 思考等级（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=关闭思考 / low / medium / high / max（2.0 旧模型不生效） |

**输出：**
- log_text: 处理日志（成功=段落数+响应元数据 finish_reason/token 消耗；空响应=⚠️警示；失败=异常+堆栈）
- scene_1 ~ scene_60: 最多 60 个场景片段
- all_scenes: 60 个场景段落按序合并为 **JSON 数组**（跳过空槽）；可直连 分镜提示词批量生成 all_scenes 输入 / 总导演 单路输入 / LLM 对话 / 存档；失败/无 Key/输入为空时为空串
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
- scene_1 ~ scene_60: 分镜脚本
- chapter_text_out / api_key_out / base_url_out / model_out: 透传
- scene_count: 分镜总数（统计实际解析出的分镜数；超过 60 时标注「N（仅显示前 60 个）」；失败/无 Key/输入为空时为空）
- all_scenes: 60 个分镜按序合并为 **JSON 数组**（跳过空槽）；可直连 分镜提示词批量生成 all_scenes 输入 / LLM 对话整段审读 / 存档；失败/无 Key/输入为空时为空串

> 输入为空（chapter_text 留空/上游未连）时直接跳过、不调 API：log_text 显示「[跳过] 输入为空…」，各槽为空。

> 两种接法：
> - 小说线：章节原文 → 总导演（章→镜一步到位）
> - 漫剧线：大纲 → Agnes 剧本生成（漫剧，场级 5–15 秒）→ 总导演（场→镜精化，每场拆 2–4 镜）→ 分镜提示词生成 → 生图/生视频
> - 分镜量大（>60 或想全量出图提示词）：总导演 all_scenes（JSON 数组）→ Agnes 分镜提示词批量生成（一根线一次出全）；整段审读连 all_scenes；单镜处理连 分镜_i / 场景_i
> - 注意：漫剧线 快节奏（5–8 秒/场）× 180 秒 ≈ 30 场 → 60+ 镜，会超出 scene_60 上限；建议漫剧线用 中速/慢热 或缩短 target_duration

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
| characters_json | STRING | "" | 角色信息 JSON（可连 资产提取 角色JSON，可选）；留空=不注入该资产块 |
| locations_json | STRING | "" | 场景信息 JSON（可连 资产提取 场景JSON，可选）；留空=不注入该资产块 |
| costumes_json | STRING | "" | 服装信息 JSON（可连 资产提取 服装JSON，可选）；留空=不注入该资产块 |
| props_json | STRING | "" | 道具列表 JSON（可连 资产提取 道具JSON，可选）；留空=不注入该资产块 |
| weather_json | STRING | "" | 天气/氛围 JSON（可连 资产提取 天气JSON，可选）；留空=不注入该资产块 |

**输出：**
- detailed_prompt: 英文提示词
- log_text: 处理日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常+堆栈）

> 输入为空（scene_text 留空/上游未连）时直接跳过、不调 API：日志显示「[跳过] 分镜文本为空…」，detailed_prompt 为跳过提示。

> 资产注入（跨镜一致性）：5 路资产 JSON 来自「Agnes 资产提取」（与总导演同源的剧本/章节），
> 任一非空即随提示词发送、模型被要求沿用其中的角色/服装/场景描述；全空时提示词中显式标注
> 「未连接资产信息，不自行脑补」——避免模型对着空标题块自由发挥。
> 全量出图（60 镜）请用下方「Agnes 分镜提示词批量生成」（其 3 路分段输出 all_prompts_1_20/_21_40/_41_60 直连「Agnes 分镜图批量生成」×3 实例 all_prompts 输入，分波出图控 RPM；≤20 条场景 all_prompts 可直连单实例一次出全）。

---

### 🎨 Agnes 分镜提示词批量生成 (AgnesScenePromptBatch)

**功能：** 将「Agnes 总导演 / Agnes 场景切分」的 all_scenes 合并输出（JSON 数组）并发生成英文生图提示词（线程池，速率可限）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_scenes | STRING | "" | 全文合并输入（一根线直连 总导演/场景切分 all_scenes 输出，JSON 数组从上到下逐条处理，最多 60 条、超出截断并在日志标注，空项跳过）；也接受**单条分镜纯文本**（连任一 分镜_i / 场景_i 或手动粘贴，视为 1 条）；空=整批跳过（零 API 调用） |
| style | COMBO | cinematic | 图像风格（整批共用） |
| characters_json / locations_json / costumes_json / props_json / weather_json | STRING | "" | 资产提取 5 路 JSON（整批共用，非空才随每条发送；留空=不注入该资产块） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型 |
| reasoning_effort | COMBO | auto | 思考等级（auto/none/low/medium/high/max；2.0 旧模型不生效） |
| max_concurrency | INT | 10 | 并发速率限制：线程池大小（1-60，默认 10）；非空分镜超过该值时排队执行，频繁 429/503 就调小 |

**输出：**
- detailed_prompt_1 ~ detailed_prompt_60: 每个分镜（all_scenes 条目序号）的英文生图提示词（可逐个连 Agnes 文生图/图生图 出关键帧）
- status: 整批执行状态 JSON `{"success":[…],"error":[…],"empty":[…]}`（**槽号=all_scenes 条目序号**，1 起；条目不足 60 时其余槽号进 empty；全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）；可直连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析
- all_prompts: 本批**成功生成**的英文提示词 JSON 数组（按槽号升序，失败/空槽不含；全空/缺 Key=空串）；≤20 条时可直连 **Agnes 分镜图批量生成** all_prompts 输入（一根线出全），>20 条请连 3 路分段 ×3 实例分波；亦可连 LLM 对话整批审改 / 存档
- all_prompts_1_20 / all_prompts_21_40 / all_prompts_41_60: 3 路**分段**成功提示词 JSON 数组（各段按槽号升序、跳过失败/空槽；该段零成功=空串）；分段直连 **Agnes 分镜图批量生成** 实例①②③ 的 all_prompts 输入（每实例 20 槽/波），每波 ≤20 张分波出图控 RPM（3 波 × 20 = 60 镜全量）

> 典型接法（分镜线 3 波出 60 镜全量，分段直连控 RPM）：
> 剧本/章节 → 总导演（all_scenes 合并槽，JSON 数组）+ 资产提取（5 路 JSON 任选）→ 分镜提示词批量生成
> （all_scenes 一根线 + 资产注入）→ 3 路分段 all_prompts_1_20/_21_40/_41_60 → 分镜图批量 实例①②③（all_prompts 一根线各连一段）
> → 各实例 image_1..20 关键帧 → SaveImage / 关键帧生视频；
> 各实例 all_images（批量图张量）→ Agnes 图像拼图 batch_images（每波一张 20 图分段总览，3 波 = 60 镜全量）；
> 视频线：3 路分段 all_prompts_1_20/_21_40/_41_60 亦可直连 Agnes 视频提示词批量 实例①②③ 的 all_prompts（每实例 20 条/波）
> → 各实例 video_prompt_1..20 一对一连 关键帧生视频 prompt 输入（image 连同波 分镜图批量 image_N，槽号对齐）= 60 镜全量视频提示词；
> ≤20 条单波场景：all_prompts（全部提示词 JSON）直连分镜图批量单实例一次出全；
> 轻量替代：场景切分 all_scenes 直连本节点；单镜处理/单条重试：连任一 分镜_i / 场景_i 纯文本（视为 1 条）；
> 资产线的参考图（三视图批量产物）可回流 图生图/关键帧生视频 保跨镜一致性（分镜图批量生成为纯文生图，不接参考图）。

> 缺 Key：60 路全输出「[错误] 缺少 API Key…」，status error=全槽、reason=缺 Key 原因（零 API 调用）；
> 全空：all_scenes 留空/条目为空 → 60 路全空串，status empty=全槽（零 API 调用）；单条失败不影响其他条。

> 旧工作流自愈：输入结构升级前（50 槽 scene_1..50 版）保存过的工作流实例，载入/排队时自动把 widget 值重映射到新 12 槽结构
> （web/js/agnes-migrate.js，旧 style/资产×5/base_url/api_key/model/reasoning_effort/max_concurrency 11 项设置原样保留）；
> 若仍见「Value not in list: style: ''」校验报错，删节点重加（右键 Agnes Novel → Agnes 分镜提示词批量生成）后重连 all_scenes 连线。

---

### 🎞️ Agnes 视频提示词生成 (AgnesVideoPromptGenerator)

**功能：** 把单条分镜（画面描述 + 可选台词/旁白）转成 Agnes 视频模型可用的英文视频提示词（运动+运镜+时序一致性+风格+质量词），LLM 一次调用

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| shot_text | STRING | "" | 分镜画面描述（连 Agnes 分镜提示词批量生成 detailed_prompt_N / all_prompts 单条，或粘贴中文分镜原文；LLM 理解后扩写为视频提示词） |
| dialogue | STRING | "" | 台词/旁白/音乐提示（可连 剧本生成 对白行）；非空才注入（视频含对白/口播/氛围音乐），空槽不占提示词篇幅 |
| style | COMBO | cinematic | 画面风格（与图像线同一套 5 档） |
| mode | COMBO | keyframe | 视频节点素材形态：keyframe=关键帧生视频（首帧已定，只描述帧后运动）；text=文生视频（无参考，完整描述）；reference=参考视频生成（<Picture N>/<Audio N> 标记指代） |
| duration | INT | 5 | 视频时长（秒，4-12）：动作量与运镜节奏按此时长设计，需与下游视频节点设置一致 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型 |
| reasoning_effort | COMBO | auto | 思考等级（可选输入；2.0 旧模型不生效） |

**输出：**
- video_prompt: 英文视频提示词（80-150 词：主体运动/运镜/运动节奏/时序一致性/光线氛围/风格/质量尾词）；直连 **Agnes 关键帧生视频 / 文生视频 / 参考视频生成** 的 prompt 输入；失败=[Error] 前缀（原因见 log_text）
- log_text: 处理日志（成功=提示词预览+响应元数据；空响应=⚠️警示；失败=异常详情+堆栈）

> 典型接法（视频线）：
> 总导演/场景切分 all_scenes → 分镜提示词批量生成 detailed_prompt_N（英文分镜提示词）
> → Agnes 视频提示词生成（shot_text，mode=keyframe，duration 与视频节点一致）
> → video_prompt → Agnes 关键帧生视频（image 连同波 分镜图批量 image_N，prompt 连 video_prompt）
> 单镜补一条视频提示词用本节点；整批 20 条/波用「Agnes 视频提示词批量生成」。

> 空输入：shot_text 留空/上游未连 → 不调 API，video_prompt=[跳过] 前缀；
> 缺 Key：video_prompt=[错误] 缺少 API Key…，日志提示三处配置入口（零 API 调用）。

---

### 🎞️ Agnes 视频提示词批量生成 (AgnesVideoPromptBatch)

**功能：** 将「Agnes 分镜提示词批量生成」任一分段输出（all_prompts 一根线输入，3 实例各连一段分波控 RPM，3 波 = 60 镜全量视频提示词）并发生成英文视频提示词（线程池，速率可限；单实例 20 槽/波）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_prompts | STRING | "" | **视频提示词一根线输入**（直连 分镜提示词批量生成 任一分段 all_prompts_1_20/_21_40/_41_60，各段 JSON 数组 ≤20 条，本实例出该波；3 实例各连一段=60 镜全量分波控 RPM，与 分镜图批量 ×3 实例节拍对称；也接受 ≤20 条 all_prompts 全量输出，JSON 数组从上到下逐条生成、超出 20 条截断并在日志标注，空项跳过）；也接受**单条英文提示词纯文本**（连任一 detailed_prompt_N 或手动粘贴，视为 1 条）；空=整批跳过（零 API 调用） |
| style | COMBO | cinematic | 画面风格（整批共用） |
| mode | COMBO | keyframe | 视频节点素材形态（整批共用）：keyframe=关键帧生视频（默认）；text=文生视频；reference=参考视频生成 |
| duration | INT | 5 | 视频时长（秒，4-12，整批共用）：动作量与运镜节奏按此时长设计，需与下游视频节点设置一致 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型 |
| reasoning_effort | COMBO | auto | 思考等级（2.0 旧模型不生效） |
| max_concurrency | INT | 10 | 并发速率限制：线程池大小（1-20，默认 10）；非空提示词超过该值时排队执行，频繁 429/503 就调小 |

**输出：**
- video_prompt_1 ~ video_prompt_20: 每条（all_prompts 条目序号）的英文视频提示词（槽号与同波 分镜图批量 image_N 天然对齐）；一对一连 **Agnes 关键帧生视频** prompt 输入；空槽（条目不足 20）=空字符串；单条异常=[Error] 前缀（原因见 status）
- status: 整批执行状态 JSON `{"success":[…],"error":[…],"empty":[…]}`（**槽号=all_prompts 条目序号**，1 起；全部请求失败时额外含 "reason" 字段）；可直连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析
- all_video_prompts: 本批**成功生成**的英文视频提示词 JSON 数组（按槽号升序，失败/空槽不含；全空/缺 Key=空串）；喂视频节点请用 20 路 video_prompt_N 一对一接法，all_video_prompts 可连 LLM 对话整批审改/存档

> 典型接法（视频线 3 波出 60 镜全量，与 分镜图批量 ×3 实例分波对称）：
> 分镜提示词批量生成 → all_prompts_1_20 → 视频提示词批量 实例①（all_prompts，波 1）
> → all_prompts_21_40 → 视频提示词批量 实例②（all_prompts，波 2）
> → all_prompts_41_60 → 视频提示词批量 实例③（all_prompts，波 3）
> 各实例 video_prompt_1..20 一对一连 关键帧生视频 prompt 输入
> （image 输入连同波 分镜图批量 image_1..20，槽号=条目序号对齐）；
> ≤20 条单波场景：分镜提示词批量 all_prompts（≤20 条）直连单实例。

> 缺 Key：20 路全输出「[错误] 缺少 API Key…」，status error=全槽、reason=缺 Key 原因（零 API 调用）；
> 全空：all_prompts 留空/条目为空 → 20 路全空串，status empty=全槽（零 API 调用）；单条失败不影响其他条。

> 视频节点是逐条生成（每节点出 1 条视频）：20 路 video_prompt_N 需 20 个 关键帧生视频 实例；
> 生成前先用 status JSON 核对成功槽（连 文本拆分 拆 3 条名单或 LLM 对话解读），避免漏槽/错槽。

---

### 🎨 Agnes 图像生成 (AgnesImageGen)

**功能：** 根据提示词生成场景图像

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 英文图像描述 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型（固定 agnes-image-2.5-flash，套件唯一图像模型；旧 2.1/2.0-flash 选项已下线，旧实例载入时自动迁到 2.5） |
| width | INT | 1920 | 图像宽度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效（已下线，2.5 模型下不生效，保留仅为兼容旧实例） |
| height | INT | 1080 | 图像高度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效（已下线，2.5 模型下不生效，保留仅为兼容旧实例） |
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

> **官方推荐提示词结构（文生图）**：Agnes Image 2.5 官方建议六槽
> `[主体]+[场景/环境]+[风格]+[光照]+[构图]+[质量要求]`，高密度时每槽列 1-3 个具体细节、
> 质量用自然语言描述（如 high detail / clean lighting），避免 masterpiece/8k 类硬标签。
> 套件内「分镜提示词生成」模板已按此结构组织（含镜头语言与风格化质量词），输出直连本节点即可。

---

### 🖼️ Agnes 图生图 (AgnesNovelImageToImage)

**功能：** 以参考图为底做编辑/变换（img2img）：主参考图必接 + 最多 5 张额外参考图（合计 6 张，
走 API 多图合成 `extra_body.image[]`）；与 图像生成 同一 agnes-image-2.5-flash 模型、共享画质档位/比例语义。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| image | IMAGE | （必接） | 主参考图：图生图以此图为底做编辑/变换；构图与主体布局会被尽量保留 |
| prompt | STRING | "" | 变换描述（建议英文）；strength<1.0 时自动追加「贴近原图」指令 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型（固定 agnes-image-2.5-flash，套件唯一图像模型；旧 2.1/2.0 实例载入时自动迁到 2.5） |
| quality | COMBO | 1K | 画质档位：1K/2K/3K/4K 与比例组合出图（2K 性价比最高） |
| aspect_ratio | COMBO | 1:1 | 输出宽高比（1:1/3:4/4:3/16:9/9:16/2:3/3:2/21:9） |
| strength | FLOAT | 0.75 | 变化强度 0-1：API 无 strength 参数，节点转成提示词指令（越低越贴近原图，1.0=完全按提示词改变） |
| n | INT | 1 | 单次生成张数：2.5 模型 API 固定出 1 张（1-4 仅旧接口） |
| reference_image_2..6 | IMAGE（可选）×5 | （不连=跳过） | 额外参考图（合计最多 6 张）：多图合成时各图角色需在 prompt 中指明 |

**输出：**
- images: 编辑/生成后的图像张量（可连 SaveImage 或视频节点）
- resolution: 本次输出的实际分辨率（WxH）

> **官方推荐提示词结构（图生图）**：Agnes Image 2.5 官方建议四槽
> `[改变要求]+[新风格/场景]+[需要添加或移除的元素]+[需要保留的元素]`，
> 显式写出「保留什么」（脸部/服装/姿势等）能显著提升编辑稳定性。示例：
> 「把背景换成夜晚的未来都市，保留人物的脸部、服装与姿势不变」
> （英文提交：Change the background to a futuristic city at night while keeping the person's face, outfit, and pose unchanged）。

> **官方推荐提示词结构（多图合成，接 reference_image_2..6 时）**：官方建议
> `[参考图角色]+[目标场景]+[图像之间的关系]+[风格/光照/构图]`——先指明每张参考图的角色
> （图 1 的角色 + 图 2 的机器人…），再写目标场景与图间关系。示例：
> 「将图 1 的角色与图 2 的机器人放进同一场科幻战斗，电影感光照，动态构图」。

> 提示词为空时直接跳过、不调 API：输出黑图占位 + 日志说明。

---

### 🎞️ Agnes 分镜图批量生成 (AgnesSceneImageBatch)

**功能：** 将「Agnes 分镜提示词批量生成」的 3 路分段输出（all_prompts 一根线输入，3 实例各连一段分波出图控 RPM，3 波 = 60 镜全量）并发生成分镜关键帧（线程池，速率可限；单实例 20 槽/波）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_prompts | STRING | "" | **分镜提示词一根线输入**（直连 分镜提示词批量生成 任一分段 all_prompts_1_20/_21_40/_41_60，各段 JSON 数组 ≤20 条，本实例出该波；3 实例各连一段=60 镜全量分波控 RPM；也接受 ≤20 条 all_prompts 全量输出，JSON 数组从上到下逐条出图、超出 20 条截断并在日志标注，空项跳过）；也接受**单条英文提示词纯文本**（连任一 detailed_prompt_i 或手动粘贴，视为 1 条）；空=整批跳过（零 API 调用） |
| quality | COMBO | 2K | 画质档位（整批共用）：2K 关键帧性价比最高；试跑用 1K 更省，4K 细节最清晰（仅新接口 2.5-flash 生效） |
| aspect_ratio | COMBO | 16:9 | 画面比例（整批共用）：关键帧默认 16:9 电影画幅；漫剧竖屏选 9:16；旧接口 2.1/2.0 按宽幅 1920x1080 / 其他 1024x1024 出图 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址（位于 api_key 紧上方） |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型 |
| max_concurrency | INT | 10 | 并发速率限制：线程池大小（1-20，默认 10）；非空提示词超过该值时排队执行，频繁 429/503 就调小 |

**输出：**
- image_1 ~ image_20: 每个分镜（all_prompts 条目序号）的关键帧张量（可接 SaveImage 存档，或逐镜连 Agnes 关键帧生视频）
- status: 整批执行状态 JSON `{"success":[…],"error":[…],"empty":[…]}`（**槽号=all_prompts 条目序号**，1 起；条目不足 20 时其余槽号进 empty；全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）；成功槽实际分辨率 WxH 见控制台日志；可直连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析
- all_images: 成功槽按槽号升序堆叠的**批量图张量 (N,H,W,3)**（N=success 条数 ≤20，同档位+比例 WxH 天然一致；失败/跳过槽不含，其黑图占位仍在 image_i 槽；零成功=空批次 (0,512,512,3)）；可直连 **Agnes 图像拼图** batch_images 总输入（每波一张 20 图分段总览拼图，拼图内部自动跳黑图双保险）

> 典型接法（分镜线 3 波出 60 镜全量，分段直连控 RPM）：
> 总导演/场景切分（all_scenes JSON 数组，≤60 条）→ 分镜提示词批量生成（+ 资产提取 5 路 JSON 任选注入）
> → all_prompts_1_20 → 分镜图批量 实例①（all_prompts 一根线，波 1 ≤20 张）
> → all_prompts_21_40 → 分镜图批量 实例②（all_prompts，波 2 ≤20 张）
> → all_prompts_41_60 → 分镜图批量 实例③（all_prompts，波 3 ≤20 张）
> 各实例 image_1..20 关键帧 → SaveImage 存档 / 关键帧生视频（逐镜）；
> 各实例 all_images → Agnes 图像拼图 batch_images（每波一张 20 图分段总览，3 波 = 60 镜全量 3 张总览）；
> ≤20 条单波场景：分镜提示词批量 all_prompts（≤20 条）或任一分段直连单实例。

> 黑图占位勿流入视频线：跳过/失败/条目不足槽输出 512×512 黑图且本节点是输出节点，
> 接 关键帧生视频 前请先用 status JSON 核对（连 文本拆分 JSON 数组模式拆 3 条名单，或 LLM 对话解读），
> 成功槽再放行，避免黑图/漏槽生成黑帧视频。

> 跨镜一致性：本节点是**纯文生图**（不接参考图）——同一角色跨分镜长相一致性靠 资产提取 → 三视图批量 产物
> 回流 图生图/关键帧生视频 节点做参考图约束；角色/场景描述词的一致性由 分镜提示词批量 的资产 JSON 注入保证。

> 缺 Key：20 路全输出黑图占位，status error=全槽、reason=缺 Key 原因（零 API 调用）；
> 全空：all_prompts 留空/条目为空 → 20 路全黑图，status empty=全槽（零 API 调用）；单条失败不影响其他条。

---

### 🎞️ Agnes 文生视频 (AgnesNovelTextToVideo)

**功能：** 文生视频：按提示词直接生成 4-12 秒视频（替代原「Agnes 视频生成」AgnesVideoGen，该节点已删除；
图参考/首尾帧请改用「Agnes 关键帧生视频」或「Agnes 参考视频生成」节点）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 视频描述（建议英文提示词，可连 Agnes 视频提示词生成 的 video_prompt） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（Agnes Video 2.5-flash） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（参数保留供展示与选择，目前仅此一项） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比：16:9 横屏 / 9:16 竖屏（API 文档列 16:9/9:16，可选缺省服务端自动处理；节点下拉保留 12 种，不支持的比例自动就近映射） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控）：一镜一主动作，时长内不换场景不切镜；与 Agnes 视频提示词生成 的 duration 保持一致 |
| seed | INT | 0 | 随机种子（0=每次随机，固定值可复现结果）；随机用输入框旁骰子按钮。本节点已禁用前端自动附加的「生成后控制」英文下拉（ComfyUI 内核按 seed 输入自动挂载、提示为硬编码英文，无法本地化；图像节点不受影响） |
| max_wait_seconds | INT | 600 | 轮询超时 |
| retries | INT | 5 | 重试次数：提交遇 503 队列满/429 限流的自动重试次数（0=不重试）。固定 30 秒/次（默认 5 次累计 150 秒/2.5 分钟；睡眠带 ±15% 随机抖动错峰，30 次上限累计 900 秒/15 分钟；503 响应带 Retry-After 头时优先按服务端指定秒数退避） |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 ComfyUI output/agnes_videos/；输出类型随环境为 VIDEO/VHS_VIDEOINFO/路径字符串），可连接 SaveVideo 预览
- resolution: 视频分辨率标注：固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）

> 旧实例自愈：本版起视频节点改为 秒数直控（删 num_frames/frame_rate）+ 固定 720P 分辨率项 +
> 模型单项（Agnes Video 2.5-flash），旧工作流实例载入/排队时 widget 值自动重映射
> （web/js/agnes-migrate.js：历史 1K/2K 档位槽丢弃 → 帧数/帧率推导秒数、模型/分辨率槽回填）；
> 若仍见「Value not in list」校验报错，删节点重加（右键 Agnes Novel → 对应视频节点）后重连。

> 原「Agnes 视频生成」节点（AgnesVideoGen，含 image 参考输入）已删除：
> 文生视频用本节点；单图首帧/首尾帧请用「🎬 Agnes 关键帧生视频」节点；
> 多张图片/音频参考请用「🎞️ Agnes 参考视频生成」节点。

---

### 🎬 Agnes 关键帧生视频 (AgnesNovelImageToVideo)

**功能：** 关键帧生视频（原「Agnes 图生视频」）：首帧必接、尾帧可选；
keyframe 首尾帧模式，接尾帧=首尾帧过渡（image→image 运动），4-12 秒直控

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| image | IMAGE | 必接 | 关键帧·首帧（first_frame）；可直连 Agnes 分镜图批量 image_N |
| prompt | STRING | "" | 视频描述（强烈建议接）；可直连 Agnes 视频提示词生成/批量 的 video_prompt 输出，免手写运镜 |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（Agnes Video 2.5-flash，keyframe 关键帧模式） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（参数保留供展示与选择，目前仅此一项） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比：16:9 横屏 / 9:16 竖屏（API 文档列 16:9/9:16，可选缺省服务端自动处理；节点下拉保留 12 种，不支持的比例自动就近映射） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控）：一镜一主动作，时长内不换场景不切镜；与 Agnes 视频提示词生成 的 duration 保持一致 |
| seed | INT | 0 | 随机种子（0=每次随机）；已禁用「生成后控制」英文下拉（同文生视频） |
| max_wait_seconds | INT | 600 | 轮询超时 |
| retries | INT | 5 | 重试次数：提交遇 503 队列满/429 限流的自动重试次数（0=不重试）。固定 30 秒/次（默认 5 次累计 150 秒/2.5 分钟；睡眠带 ±15% 随机抖动错峰，30 次上限累计 900 秒/15 分钟；503 响应带 Retry-After 头时优先按服务端指定秒数退避） |
| end_frame_image | IMAGE | - | 关键帧·尾帧（可选，last_frame；不接=仅按首帧生成） |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 output/agnes_videos/，输出类型随环境为 VIDEO/VHS/路径）
- resolution: 视频分辨率标注：固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）

> 多张参考图/音频参考请用「🎞️ Agnes 参考视频生成」节点。
> 旧实例自愈同「文生视频」：秒数直控（删 num_frames/frame_rate）+ 720P 分辨率项 + 模型单项，旧实例 widget 值由 agnes-migrate.js 自动重映射。

---

### 🎞️ Agnes 参考视频生成 (AgnesVideoReference)

**功能：** 参考素材生视频（reference 模式）：最多 5 张参考图
（image_1~5，提示词用 `<Picture N>` 指代）+ 最多 3 段参考音频
（audio_1~3，提示词用 `<Audio N>` 指代；音频为本地文件路径或公开 URL，
本地文件自动转 Base64 Data URI，单段 <15MB）。至少提供一种媒体参考，4-12 秒直控

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 视频描述；`<Picture 1>~5` / `<Audio 1>~3` 指代参考素材（可直连 Agnes 视频提示词生成 mode=reference 的输出） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖全局地址 |
| api_key | STRING | sk-你的Key | Agnes AI API Key |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（Agnes Video 2.5-flash，reference 模式支持图片+音频参考） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（参数保留供展示与选择，目前仅此一项） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比：16:9 横屏 / 9:16 竖屏（API 文档列 16:9/9:16，可选缺省服务端自动处理；节点下拉保留 12 种，不支持的比例自动就近映射） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控）：一镜一主动作，时长内不换场景不切镜；与 Agnes 视频提示词生成 的 duration 保持一致 |
| seed | INT | 0 | 随机种子（0=每次随机）；已禁用「生成后控制」英文下拉（同文生视频） |
| max_wait_seconds | INT | 600 | 轮询超时 |
| retries | INT | 5 | 重试次数：提交遇 503 队列满/429 限流的自动重试次数（0=不重试）。固定 30 秒/次（默认 5 次累计 150 秒/2.5 分钟；睡眠带 ±15% 随机抖动错峰，30 次上限累计 900 秒/15 分钟；503 响应带 Retry-After 头时优先按服务端指定秒数退避） |
| image_1 ~ image_5 | IMAGE | - | 参考图片（一张必接或可只接音频；上限 5 张） |
| audio_1 ~ audio_3 | STRING | "" | 参考音频（本地路径或公开 URL；上限 3 段） |

**输出（含输出描述）：**
- video: 视频（MP4 保存到 output/agnes_videos/）
- resolution: 视频分辨率标注：固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）

> 旧实例自愈同「文生视频」：秒数直控（删 num_frames/frame_rate）+ 720P 分辨率项 + 模型单项，旧实例 widget 值由 agnes-migrate.js 自动重映射。

---

### 🎞️ Agnes 视频任务提交 (AgnesVideoTaskSubmit)

**功能：** 视频任务异步提交（两段式·提交段）：输入与退避策略与「Agnes 文生视频」一致
（9 个输入，唯一差异=无 max_wait_seconds 保留项——本节点只提交不轮询，轮询时限在 收取 节点 timeout 设置），
但只执行「提交」这一段——POST 拿到任务 ID 后秒级返回，不轮询不下载，画布立刻解放。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING | "" | 视频描述（建议英文，可连 Agnes 视频提示词生成/批量 的 video_prompt） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL；task_url 输出按此域名拼装（跨域名提交也拼对） |
| api_key | STRING | sk-你的Key | Agnes AI API Key（留空跟随全局） |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（Agnes Video 2.5-flash） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（展示项，同文生视频） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比（同文生视频，不支持比例自动就近映射） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控，同文生视频） |
| seed | INT | 0 | 随机种子（同文生视频，已禁用「生成后控制」英文下拉） |
| retries | INT | 5 | 提交遇 503 队列满/429 限流的自动重试次数（退避节奏同文生视频：固定 30 秒/次，默认 5 次累计 150 秒，睡眠带 ±15% 抖动；上限放宽至 120 次累计 3600 秒/60 分钟，文生视频等节点仍为 30） |

**输出（含输出描述）：**
- task_url: 完整轮询 URL（含域名 /agnesapi?video_id=…&model_name=…；域名跟随本节点请求地址，跨域名提交也拼对）——直连 收取 节点的 task_url 输入；提交失败="0" 标记（未生成任务，收取节点见 "0" 直接跳过收取）
- status: 任务状态：成功=`submitted: video_id=…`；失败=Agnes 服务端错误响应内容（HTTP 503 队列满/400 参数错误等的原文诊断）
- api_key: API Key 穿透：提交时实际使用的 Key（节点输入非空=输入值，否则=全局回退值）——直连 收取 节点的 api_key 输入，收取端免再配 Key（提交失败/缺 Key 短路时为空）
- task_url_key: 单线双参 JSON：{"task_url": 轮询 URL（失败=0 标记）, "api_key": 实际使用的 Key}（与 task_url/api_key 两路输出同源）——直连 批量收取 节点的 task_i 槽（N 个提交实例直连 N 个槽，**0 个中间节点**）：一根线带齐 URL+Key 两个参数，各槽 Key 可全不同（条目自带 Key 只作用于本任务，互不干扰）

> 两段式用法：提交节点秒级返回 → 出片期间画布可跑其他工作流（分镜图/下一部小说）→
> 之后右键运行 收取 节点收片（自动下载到 output/agnes_videos/）。
> 60 镜线接法两种：
> ① 逐个收取：视频提示词批量 ×3 分段 → 视频任务提交 ×3（几分钟提交完 60 任务）
> → 视频任务收取 ×N 实例（一任务一实例，右键部分执行，自动下载）→ 60 镜视频全量落盘；
> ② 批量收取：同上提交 ×60（分 3 波，每波 20 实例）→ 每波 20 个实例的 task_url_key 输出
> 直连 1 个 视频任务批量收取 实例的 task_1…task_20（0 个中间节点，各槽 Key 可全不同）
> → 3 实例 × 20 路 video 直连 Save Video 全量落盘（总时长≈max 各视频渲染时长，非 sum）。

---

### 📥 Agnes 视频任务收取 (AgnesVideoTaskCollect)

**功能：** 视频任务异步收取（两段式·收取段，单任务）：输入 1 路 task_url（完整轮询 URL
自带域名，跨域名提交的任务同样可查），节点内轮询查询（首查前 60s、之后每 5s），
completed 自动下载 mp4（3 次重试 2/5/10s），输出视频（环境动态类型，同 文生视频）+ 状态。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| task_url | STRING | "" | 完整轮询 URL：直连 Agnes 视频任务提交 的 task_url 输出（含域名，跨域名可查）；留空=整节点跳过（status 输出 empty）；收到 "0"=上游提交失败标记，跳过收取、status 输出 error 内容 |
| api_key | STRING | sk-你的Key | 轮询查询需 Bearer 鉴权，可直连 视频任务提交 的 api_key 穿透输出（提交端实际用的 Key，免再配）；留空跟随全局；域名已在 task_url 里，无需再填请求地址 |
| timeout | INT | 600 | 本节点最长等待（秒，默认 10 分钟）：到点仍生成中=processing（不算失败），再次右键运行本节点即继续查（任务还在服务端）；视频一般 3-10 分钟出片，默认 10 分钟通常一趟收完，慢了就再点一次 |

**输出（含输出描述）：**
- video: MP4 文件（落盘 ComfyUI output/agnes_videos/），输出类型随环境三档（与 文生视频 同源动态探测）：原生 ComfyUI = VIDEO（VideoFromFile 惰性文件引用，**可直连 Save Video**：SaveVideo 读盘重编码到 output/video/ 并在输出预览面板播放）/ 装 VHS = VHS_VIDEOINFO（可接 VHS 播放器）/ 无视频节点 = 路径字符串；无视频文件时（任务未完成/失败/未连接输入/0 标记/缺 Key）：原生环境输出 NO_VIDEO_ 前缀的 2 秒黑帧 720P 占位 mp4（status 携带 error 内容、队列不被打断；PyAV 不可用时回退红错），VHS/STRING 环境返回空值不崩
- status: 任务状态：completed=服务端视频 URL（有效期内可浏览器直接播放/下载）；failed=Agnes 服务端错误响应内容（任务级 failed 与下载失败诊断）；processing=到轮询超时未完成（可再次右键运行本节点继续查询）；error=收到 0 标记（上游 提交 失败，跳过收取，原因见 提交 节点 status）；empty=未连接 task_url

> 无文件态黑帧占位约定：原生视频环境下 video 槽必须交接真实文件（空引用会令下游 Save Video 崩溃），故 收到 0 标记（上游提交失败）/failed/processing/empty/缺 Key 时输出 NO_VIDEO_ 前缀黑帧占位 mp4（PyAV 现场编码 2 秒 720P，约 12KB），**status 携带完整 error 内容、队列不被打断**（如「processing: 已等待 600 秒任务未完成，可再次运行本节点继续查询」「error: 上游 提交 未成功（task_url=0 标记），等 5-10 分钟重跑 提交 节点」）；出片/提交成功后再次右键运行即得真视频；任务仍在服务端，不重复计费。占位文件靠 NO_VIDEO_ 前缀自证（批量收取文件名带槽号），勿当真实视频用；PyAV 不可用时回退旧红错约定。文生视频等节点仍维持原红错约定。

---

### 📥 Agnes 视频任务批量收取 (AgnesVideoTaskCollectBatch)

**功能：** 视频任务异步批量收取（两段式·收取段，≤20 任务并发）：把 N 个视频任务交给
一个节点，线程池并发轮询收取（免 N 个 收取 实例逐个右键），全部 settled 才返回；
completed 自动下载到 output/agnes_videos/（3 次重试）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_task_url_keys | STRING（多行） | "" | **合并输入（面板置顶，优先于 20 槽逐一连线）**：直连「Agnes 视频多任务并发提交」的 all_task_url_keys 输出（20 元素保位 JSON 数组，一行带齐 N 个任务句柄）；非空时按条目序填充 task_1..task_20 槽（超 20 条截断，video_1..20 按序输出）：条目可为 ① task_url_key 单线双参 JSON（{"task_url","api_key"}）② "0"=上游提交失败标记（该槽跳过收取记 error，**默认视频占位填充**）③ 空（记 empty 槽号保位）④ 纯轮询 URL；空=走下方 20 槽逐一连线旧语义（旧工作流零影响） |
| task_1…task_20 | STRING ×20 | ""（各槽） | 20 个任务输入，**task_i ↔ video_i 一一对应**（第 i 输入出第 i 路视频）：① 视频任务提交 的 task_url_key 单线双参 JSON（{"task_url","api_key"}，一行带齐 URL+Key，N 个提交实例直连 N 槽 0 中间节点，各槽 Key 可全不同——条目自带 Key 只作用于本任务）② 纯轮询 URL 字符串（Key 走 api_key 兜底输入→全局配置）③ "0"=上游提交失败标记（该槽跳过收取记 error，默认视频占位填充）④ 未连接/空=该槽跳过（记 empty，槽号保位）；全空=整批跳过（零 API 调用） |
| api_key | STRING | （留空=全局） | 条目未自带 api_key 时的兜底 Key（可直连某 提交 节点的 api_key 穿透输出，单 Key 场景全体共用）；条目自带 Key 的优先用自带 |
| timeout | INT | 600 | 单任务最长等待（秒，默认 10 分钟，同 单收取）：到点仍生成中=processing（不算失败），再次右键运行本节点即继续查未完成任务（全批 settled 才返回） |
| max_concurrency | INT | 10 | 线程池并发（同时轮询任务数 1-20，默认 10）：非空条目超过该值时排队执行；轮询是轻 GET，10 并发压力很小 |

**输出（22 槽，含输出描述）：**
- video_1…video_20: 第 i 条任务（tasks 第 i 条）的视频，环境动态类型（同 文生视频/单收取 三档）：原生 ComfyUI=VIDEO（VideoFromFile 惰性引用，**可直连 Save Video**）/ VHS=VHS_VIDEOINFO / 无视频节点=路径字符串；completed=真实文件，failed/processing/empty/0 标记/缺 Key=NO_VIDEO_ 前缀黑帧占位（原生环境，文件名带槽号，队列不打断）或空值（VHS/STRING）
- status: 整批执行状态 JSON（槽号 1 起保位）：{"success":[completed 槽],"failed":[服务端失败/下载失败/缺 Key/网络异常槽],"processing":[到 timeout 未完成槽],"empty":[空输入槽],"error":["0" 标记槽],"details":{槽:原因}}；可连 文本拆分（JSON 数组模式）拆成名单做对接分析
- all_video_paths: 20 元素 JSON 数组（与 video_i 槽下标一一对应）：completed=本地落盘路径（下载失败时=服务端 URL），其余=空串；JSON 一行带走 20 条路径清单（手动拷片/投喂其他工具/台账记录）

> 批量收取用法 A（20 槽逐一连线，60 镜线）：视频提示词批量 ×3 分段 → 视频任务提交 ×60（分 3 波，每波 20 实例）
> → 每波 20 个实例的 task_url_key 输出 直连 1 个 视频任务批量收取 实例的 task_1…task_20
> （0 个中间合并节点，各槽 Key 可全不同）
> → 3 实例 × 20 路 video 直连 Save Video 全量落盘。
> 批量收取用法 B（合并输入，提交侧单节点，20 镜/波）：视频提示词批量（分段）
> → Agnes 视频多任务并发提交（all_prompts 一根线，提示词串行 × 池顺序短路）
> → all_task_url_keys 一根线直连 1 个 批量收取 实例的 all_task_url_keys 合并输入
> （0 中间节点；"0" 条目跳过收取并默认视频占位填充）→ 20 路 video 按序直连 Save Video。
> 与 单收取 的差别：一个节点收 20 任务（总时长≈max(各视频渲染时长)，非逐任务右键的 sum）；
> processing 槽再次右键运行本节点即继续查（completed 任务重查秒回不重下），不重复计费。

---

### 🔑 Agnes API Key 池配置 (AgnesApiKeyPool)

**功能：** 多端点 API Key 池数据源（纯数据节点，零 API 调用）：把多组「Base URL + API Key」
条目（国内 + 国外 Agnes 平台不同账号等）聚合成一份池 JSON，输出给「Agnes 视频任务并发提交」
节点做多端点顺序短路提交——一端队列满 503 时另一端的绿窗可接住任务。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| pool_json | STRING（多行） | "" | 池条目 JSON 对象数组：`[{"base_url": "https://api.agnes-ai.cn/v1", "api_key": "sk-…（国内）", "name": "国内"}, {"base_url": "https://api.agnes-ai.com/v1", "api_key": "sk-…（国外）", "name": "国外"}]`；api_key 必填（缺 Key 条目自动跳过）；base_url 可空=跟随全局配置；name 可选仅展示（供 池报告 辨识）；重复 Key 自动去重（首个生效）；一行或多行均可 |
| include_global | BOOLEAN | 否 | 启用时把当前全局 Key（API Key 配置节点 / 环境变量 AGNES_API_KEY / api_key_config.json / config.yaml，同 单提交 节点回退链）作为**末尾条目**并入池（已在池中则不重复，全局 Key 为空则跳过）——「单账号」场景免手贴，池退化为 1 条目（行为等同 单提交 节点） |

**输出（4 路，均 STRING）：**
- pool_json: 规范化池 JSON（一行数组）：直连「Agnes 视频任务并发提交」/「Agnes 视频多任务并发提交」的池输入；无有效条目="0" 标记（下游见 "0" 零请求短路，同 单提交 "0" 标记族语义）
- pool_count: 池内有效条目数（"0"=空池）
- pool_report: 掩码清单（每条目一行：`#i 名称 | 请求地址(空=全局) | sk-…****…`）：人工核对池内容，Key 已掩码可安全显示
- status: 配置结果：`ok: 池内 N 条（含并入全局说明）` / `error: 原因`（JSON 解析错误 / 无有效条目 / 池为空）

> 池线接法 A（逐镜头多实例）：API Key 池配置（pool_json）→ 视频任务并发提交 ×N（N=镜头数/池容量）
> → task_url_key 直连 批量收取 task_1…task_20（各槽 Key=各胜出条目 Key，互不干扰，批量收取 零改动）
> → status/pool_report 逐条目 JSON 直接人工查看（或接 LLM 对话节点做台账）。
> 池线接法 B（多任务单节点，20 镜/波）：API Key 池配置（pool_json）
> → 视频多任务并发提交（all_prompts 直连 视频提示词批量 all_video_prompts，提示词串行 × 池短路）
> → all_task_url_keys 一根线直连 批量收取 all_task_url_keys 合并输入。

---

### 🎞️ Agnes 视频任务并发提交 (AgnesVideoTaskSubmitPool)

**功能：** 视频任务多端点池提交（异步两段式·提交段·顺序短路 B）：「视频任务提交」的池版本——
同一提示词在「API Key 池配置」输出的池 JSON（多组 Base URL+Key 条目）中**按池序顺序试探**：
#1 成功即停、后续条目零请求（零浪费）；#1 队列满 503 时 #2 的绿窗可能正好接住任务。
只执行「提交」段——拿到任务 ID 秒级返回，不轮询不下载（轮询/收取在 收取/批量收取 节点）。
输入与退避策略同「Agnes 视频任务提交」（唯一差异：base_url + api_key 两个 widget
换成 pool_json 池输入）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| prompt | STRING（多行） | "" | 视频描述（建议英文，全池条目共用；可连 视频提示词生成/批量 的 video_prompt） |
| pool_json | STRING（多行） | "" | 直连「Agnes API Key 池配置」的 pool_json 输出（多组 Base URL+Key 条目 JSON 数组）；也可直接粘贴池 JSON；"0" 标记=上游池无有效条目（零请求短路）；条目 base_url 可空=跟随全局 |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（全池条目共用） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（展示项，同 单提交） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比（同 单提交，不支持比例自动就近映射） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控，同 单提交） |
| seed | INT | 0 | 随机种子（0=每次随机；全池条目共用同一种子） |
| retries | INT | 5 | 与 单提交 retries 同机制：一轮=按池序全条目试探一次（一条目一次 POST），整轮全灭固定 30 秒/轮退避（±15% 抖动；Retry-After 头优先）；默认 5（6 轮、累计 150 秒）；上限 120（121 轮、累计 3600 秒/60 分钟，**累计等待与池大小无关**）；400/401/403/404 条目标 dead 后续轮跳过（不反复打无效 Key）、全灭提前终止 |

**输出（5 路，均 STRING；面板自上而下，status 置最下）：**
- task_url: 成功=**胜出条目**的完整轮询 URL（含该条目域名 /agnesapi?video_id=…&model_name=…，跨域名拼对）——直连 收取/批量收取；失败="0" 标记
- api_key: API Key 穿透：胜出条目实际使用的 Key（失败=空串）——直连 收取 的 api_key 输入免再配
- task_url_key: 单线双参 JSON {"task_url", "api_key"}（胜出条目 URL+Key 一行带齐）——直连 批量收取 task_i 槽，**批量收取 节点零改动**（各槽 Key 可全不同）
- pool_report: 逐条目 JSON 数组 `[{i, base_url, key(掩码), attempts, result}]`（result ∈ success@roundN / dead:HTTPxxx / 末次诊断 / 未请求(短路跳过)）——逐条目矩阵 JSON，人工查看或接 LLM 对话节点做台账；零请求短路=空数组 []
- status: 成功=`submitted: video_id=…（池 #i / base_url）`；失败=末次诊断原文（503 队列满等）+ 退避轮数/累计等待 + 建议（5-10 分钟重跑 / 增配池条目 / 错峰）；鉴权全灭=`池内全部条目 dead` 提前终止诊断

> 池线用法（与 60 镜线同构）：API Key 池配置（国内+国外多账号条目）
> → 视频任务并发提交 ×N → task_url_key 直连 批量收取 task_1…task_20
> → 20 路 video 直连 Save Video；status/pool_report 逐条目 JSON 直接人工查看（或接 LLM 对话节点做台账）。
> 何时用：单 Key 提交全 503 video_queue_full（分钟级持续态）且池内条目分属**不同容量池**
> （不同账号/国内国外不同平台端点）——一端满、另一端绿窗时任务直接落地；
> 池内条目若共享同一平台全局限额，并发探测收益有限（仍可用，顺序短路保证成功时零浪费）。

---

### 🎞️ Agnes 视频多任务并发提交 (AgnesVideoTaskSubmitBatch)

**功能：** 视频任务多端点池**多任务**提交（异步两段式·提交段，**提示词串行 × 池短路**）：
「Agnes 视频任务并发提交」的多任务版本——1 路 all_prompts 合并输入（JSON 数组 ≤20 条，
直连「Agnes 视频提示词批量」任一分段 all_video_prompts 输出）替代单提示词输入；节点内部
**挨个循环**每个提示词——一次只提交一个（绝不同双提示词并发，队列压力 = 逐个「并发提交」
实例节拍），每条提示词走多端点 Key 池顺序短路（#1 成功即停零浪费，retries 机制同 并发提交，
复用现成 submit_video_task_pool 实现）。单条失败=该槽 "0" 标记，继续下一条不整批中止。
最坏总时长 = N 条 × (1+retries) × 30 秒（retries=5 默认 → 单条最坏 ≈3 分钟，20 条全批最坏 ≈60 分钟）。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_prompts | STRING（多行） | "" | 合并输入：① JSON 数组（直连 视频提示词批量 all_video_prompts，一波 20 条；条目从上到下挨个串行提交，最多 20 条超出截断，空项跳过）② 单条纯文本（视为 1 任务）③ 空=整批跳过（零 API 调用） |
| pool_json | STRING（多行） | "" | 直连「Agnes API Key 池配置」的 pool_json 输出（多组 Base URL+Key 条目 JSON 数组）；"0" 标记=上游池无有效条目（全槽 0 标记零请求短路）；条目 base_url 可空=跟随全局 |
| model | COMBO | agnes-video-2.5-flash | 视频生成模型（整批共用） |
| resolution | COMBO | 720P | 输出分辨率：固定 720P（展示项，同 并发提交） |
| aspect_ratio | COMBO | 16:9 | 画面宽高比（同 并发提交，不支持比例自动就近映射；整批共用） |
| seconds | INT | 5 | 视频时长（秒，4-12 直控；与上游 视频提示词批量 duration 保持一致；整批共用） |
| seed | INT | 0 | 随机种子（0=每条随机，固定值可复现；整批共用同一种子） |
| retries | INT | 5 | 与 并发提交 retries 同机制（**作用于每条提示词**）：一轮=按池序全条目试探一次，整轮全灭固定 30 秒/轮退避（±15% 抖动；Retry-After 头优先）；默认 5（单条 6 轮、最坏 150 秒）；上限 120（单条最坏 3600 秒/60 分钟）；400/401/403/404 条目标 dead 后续轮跳过 |

**输出（22 槽，均 STRING；顺序对齐「Agnes 视频提示词批量」video_prompt_1..20 + status + all_video_prompts，提示词槽 i ↔ 任务句柄槽 i）：**
- task_url_key_1…task_url_key_20: 第 i 条提示词（all_prompts 非空条目顺序编号）的任务句柄：成功=单线双参 JSON `{"task_url","api_key"}`（与 并发提交 task_url_key 同格式，可直连 批量收取 task_i 槽或 单收取）；**失败="0" 标记**（全轮全灭/池不可用，收取端见 0 自动跳过并默认视频占位填充，原因见 status details）；空槽（条目不足 20/该位空条目）=空字符串（槽号 1 起保位）
- status: 整批执行状态 JSON：`{"success":[成功槽号],"failed":[失败槽号],"empty":[未使用槽号],"details":{槽号:失败原因}}`；可直接连 文本拆分（JSON 数组模式）拆名单做对接分析，或接 LLM 对话解读哪些槽需重跑
- all_task_url_keys: 20 元素保位 JSON 数组（与 20 路 task_url_key_i 同序逐槽一致：成功条目=单线双参 JSON 对象、失败条目=字符串 "0"、空槽=空字符串；零提示词输入=空字符串整体）——**一根线直连「Agnes 视频任务批量收取」的 all_task_url_keys 合并输入**，或接 LLM 对话整批台账/存档

> 接法（视频线·分波全量异步，20 镜/波）：API Key 池配置（pool_json）
> → Agnes 视频多任务并发提交（all_prompts 直连 视频提示词批量 all_video_prompts）
> → all_task_url_keys 一根线直连 批量收取 all_task_url_keys 合并输入
> （等价：20 路 task_url_key_i 直连 批量收取 task_1…task_20 逐一接法）
> → 20 路 video 按序直连 Save Video。
> 何时用：一波 20 镜要**全部异步提交**但又不想拉 20 个 并发提交 实例——本节点单实例串行
> 逐条提交（RPM 压力同单实例节拍），60 镜=3 实例各接一段 all_video_prompts 分波。

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

### 📐 Agnes 三视图批量生成 (AgnesTurnaroundBatch)

**功能：** 三视图提示词合并输入驱动的批量三视图出图节点：
1 路 all_prompts 全文合并输入（↔ 三视图提示词批量 all_turnaround_prompts 输出，
一根线直连；也接受单条三视图提示词纯文本，视为 1 条），线程池并发请求图像 API，
`max_concurrency` 限制同时请求数（默认 10，超出排队执行）。
all_prompts 空项=跳过该槽（不发请求，输出黑图占位，槽号保位）；
单槽失败不影响其他槽，失败槽同样黑图占位。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_prompts | STRING(多行) | "" | 三视图提示词合并输入：① JSON 数组（三视图提示词批量 all_turnaround_prompts 输出直连，条目从上到下逐条出图，最多 20 条超出截断，空项=跳过该槽槽号保位）② 单条三视图提示词纯文本（连 three_view_prompt_i 或粘贴，视为 1 条）③ 空=整批跳过（零 API 调用） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖 |
| api_key | STRING | 留空自动加载 | Agnes AI API Key |
| model | COMBO | agnes-image-2.5-flash | 图像生成模型 |
| quality | COMBO | 2K | 档位：1K/2K/3K/4K |
| aspect_ratio | COMBO | 21:9 | 三视图推荐宽幅（21:9 / 16:9） |
| max_concurrency | INT | 10 | 并发速率限制（线程池大小，1-20）：非空提示词超过该值时排队；频繁 429/503 就调小，配额充足可拉满 |

**输出（22 路）：**
- image_1..image_20：各槽（all_prompts 第 i 条）三视图张量（成功=真实图；跳过/失败=512×512 黑图占位），可接 SaveImage 存档或作参考图
- status：整批执行状态 JSON `{"success":[成功槽号],"error":[失败槽号],"empty":[空输入槽号]}`（**槽号=all_prompts 条目序号，1 起保位**；成功槽的实际分辨率 WxH 见控制台日志）；
  全部请求失败（success 为空且 error 非空）时额外含 `"reason"` 字段——各槽同一原因=字符串，不同=槽号→原因映射；
  可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，或接 LLM 对话让模型解读哪些槽需要重试
- all_images：成功槽按槽号升序堆叠的批量图张量 **(N,H,W,3)**（N=success 条数，同档位+比例出图 WxH 一致；失败/跳过槽不含；零成功=空批次 (0,512,512,3)），
  可一根线直连 Agnes 图像拼图 batch_images 总输入出总览拼图（拼图内部跳黑图双保险；N=0 时拼图回落 512 黑图 count=0/0）

> 典型接法（资产线，一根线到底）：
> `资产提取.角色JSON → 资产提示词批量(all_items) → all_prompts → 三视图提示词批量(all_prompts) → all_turnaround_prompts → 三视图批量(all_prompts) → all_images → 图像拼图(batch_images) → 总览拼图`
> 轻量单槽：`三视图提示词批量 three_view_prompt_i 单条纯文本 → all_prompts`（视为 1 条）。
> 日志：`[Agnes 三视图批量] 输入=JSON 数组，条目 N（超 20 条已截断），非空 M 条，并发 K`，每槽完成打印 `#i 成功 WxH` / `#i 失败 原因`，收尾打印 `完成：成功 X/N` + `状态: success=[…] error=[…] empty=[…]` + `all_images: N 张成功图 → (N,H,W,3) 批量张量`。
> 想看全批不用 20 个 预览图像：`all_images → 🧩 图像拼图(batch_images) → 预览图像/SaveImage`（旧接法 image_1..20 手接仍可用）。
> 旧实例（26 槽结构）载入时 web/js/agnes-migrate.js 自动迁移 widget 值（26→7），无需手工重建。

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
> （20 条批量版见下方「三视图提示词批量生成」章节）

---

### ✍️ Agnes 三视图提示词批量生成 (AgnesTurnaroundPromptBatch)

**功能：** 资产提示词合并输入驱动的批量三视图提示词生成节点：
1 路 all_prompts 全文合并输入（↔ 资产提示词批量 all_prompts 输出，一根线直连；
也接受单条资产提示词纯文本，视为 1 条），线程池并发生成三视图英文提示词，
`max_concurrency` 限制同时请求数（默认 10，超出排队执行），
20 路 three_view_prompt + status + all_turnaround_prompts 输出。
参数与单条「Agnes 三视图提示词生成」完全一致，整批共用。
all_prompts 空项=跳过该槽（槽号保位）；单槽失败不影响其他槽。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_prompts | STRING(多行) | "" | 资产提示词合并输入：① JSON 数组（资产提示词批量 all_prompts 输出直连，条目从上到下逐条生成，最多 20 条超出截断，空项=跳过该槽槽号保位）② 单条资产提示词纯文本（连 english_prompt_i 或粘贴，视为 1 条）③ 空=整批跳过（零 API 调用） |
| subject_type | COMBO | 角色 | 角色/物品道具/服装/场景/载具/通用（整批共用，决定分栏布局指令） |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖 |
| api_key | STRING | 留空自动加载 | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（整批共用） |
| reasoning_effort | COMBO | auto | 思考等级（整批共用） |
| max_concurrency | INT | 10 | 并发速率限制（线程池大小，1-20）：非空提示词超过该值时排队；频繁 429/503 就调小 |

**输出（22 路）：**
- three_view_prompt_1..three_view_prompt_20：各槽（all_prompts 第 i 条）完整三视图英文提示词（主体全部细节 + 分栏布局「左 1/3 特写 + 右 2/3 三视图」
  + 虚幻引擎渲染/PBR/柔和漫射光 + 纯白背景干净极简无阴影 + 8K 质量尾词），可直接接 三视图生成(subject_desc)；
  空输入=空字符串；失败=`[Error]` 前缀文本
- status：整批执行状态 JSON `{"success":[成功槽号],"error":[失败槽号，含空响应],"empty":[空输入槽号]}`（**槽号=all_prompts 条目序号，1 起保位**）；
  全部请求失败（success 为空且 error 非空）时额外含 `"reason"` 字段——各槽同一原因=字符串，不同=槽号→原因映射；
  可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，
  或接 LLM 对话让模型解读哪些槽需要重试（空响应=API 200 但正文为空，常见为思考预算耗尽：降 reasoning_effort / 换 agnes-2.5-flash）
- all_turnaround_prompts：本批成功生成的三视图英文提示词 JSON 数组（ensure_ascii=False，按槽号升序；失败/空槽不含；全空/缺 Key/零成功=空串），
  可一根线直连 Agnes 三视图批量生成 all_prompts 输入（批量出三视图参考图）

> 典型接法（资产线批量，一根线到底）：
> `资产提取.角色JSON → 资产提示词批量生成(all_items) → all_prompts → 三视图提示词批量生成(all_prompts) → all_turnaround_prompts → 三视图批量生成(all_prompts)`
> 轻量单槽：`资产提示词批量 english_prompt_i 单条纯文本 → all_prompts`（视为 1 条）；也可 20 个 三视图提示词生成 实例逐条输出后手工拼 JSON 数组填入。
> 日志：`[Agnes 三视图提示词批量] 输入=JSON 数组，条目 N（超 20 条已截断），非空 M 条，并发 K`，每槽完成打印 `#i 成功 N 字 预览...` / `#i 失败 原因`，收尾打印 `完成：成功 X/N` + `状态: success=[…] error=[…] empty=[…]` + `all_turnaround_prompts: N 条成功提示词 → JSON 输出`。
> 旧实例（26 槽结构）载入时 web/js/agnes-migrate.js 自动迁移 widget 值（26→7），无需手工重建。

---

### 🧩 Agnes 图像拼图 (AgnesImageMosaic)

**功能：** 批量节点的 1 路批量图总输入（batch_images，(N,H,W,3) 批量张量）或
20 路 IMAGE 输出「动态数量展示」：汇聚成 1 张拼图，一个 预览图像 节点看全批，
黑图占位自动过滤（双保险），有效图数 N 动态决定网格行数。

**全部 21 个输入均为 optional（可选）**：不连线的输入自动跳过、**前端不画红框**——只连 1 根 batch_images 时其余 20 个 image_i 不会发红（旧版本 20 槽声明为 required 会全红，属视觉告警而非报错，已修正为可选语义）；都不连时回落 512 黑图占位 + count=0/20 + 日志提示。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| batch_images | IMAGE（可选） | （不连=走 20 槽） | 批量图总输入：连 三视图批量/分镜图批量 的 all_images 批量张量（(N,H,W,3)；也接受单张 (H,W,3)/(1,H,W,3)）；**连上时优先用它拼（20 槽忽略，日志标注）**；不连则照旧走 20 槽（旧图完全兼容） |
| image_1..image_20 | IMAGE（可选）×20 | （不连线=跳过） | 第 i 个图像槽：连 三视图批量生成 的 image_i（或任意 IMAGE 输出）；未连接=该槽自动跳过不参与拼图（不红） |

**输出：**
- mosaic: 2 列 × ⌈N/2⌉ 行网格拼图张量（单元格等宽、深灰底 + 8px 间距、每格左上角标条目号 #i；
  全黑占位与未连接槽被过滤；全无效时回落 1 张 512×512 黑图占位，可连 预览图像 / SaveImage）
- count: 有效图数「N/分母」（分母=20 槽模式为 20、batch_images 模式为其条目数 N；N=0 时 count=0/0）

> 规则细节：未连接槽（None）与全零张量（批量节点跳过/失败的 512×512 黑图占位）不计入 N；
> batch_images 拆条后每张再走同一套黑图过滤（三视图批量黑图占位若混入也会被跳过）；
> 单元格宽度 = min(所有有效图最大图宽, 1600px)，各图等比缩放；
> 纯本地 PIL 合成，不调 API、无需 API Key；拼图为缩略级总览，看细节仍接单路 image_i。
>
> 典型接法（一根线）：`三视图批量生成.all_images (N,H,W,3) → 图像拼图.batch_images → 预览图像/SaveImage`（资产线全链路收尾）；
> 旧接法 `image_1..20 → 图像拼图` 仍可用；配合 status JSON（全部失败时含 reason）核对哪些槽没出图。
> 日志：`[Agnes 图像拼图] 有效 N/分母 张（来源: batch_images 批量张量（N 条…） / image_1..20 槽）→ 拼图 W×H（行数 × 2 列，条目 […]）`。

> 提示词参考：本节点是**纯本地拼图**（无提示词、不调 API）；若多张参考图需要**经 API 出图**
> （多图合成），走「Agnes 图生图」节点的 reference_image_2..6（合计最多 6 张），
> 提示词按官方多图合成结构写：`[参考图角色]+[目标场景]+[图像之间的关系]+[风格/光照/构图]`
> （详见「Agnes 图生图」章节）。

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
| JSON 对象 | 批量节点 status 输出（`{"success":[1,2],"error":[3],"empty":[4,...]}`） | 逐键一条：`success: [1, 2]` / `error: [3]` / `empty: [4, ...]`，3 条名单供 LLM 对话/人工分析 |
| 【】括号块 | LLM 输出的定妆文（「【苏尘】黑发男子…【柳如烟】白衣…」） | 每个【名】起头、到下一个【前 |
| 编号列表 | 「1. … 2、… 一、… (3) …」格式 | 每个编号行一条 |
| 空行段落 | 空行分隔的多段文本 | 每个段落一条 |

**输出：**
- 第 1 条 ~ 第 20 条: 拆分出的独立文本（不足 20 条的槽位为空）
- 条数: 实际条目总数（超过 20 条时显示「N（仅显示前 20 条）」）
- 原文透传: 原始输入（并联其他节点或存档）
- all_items: 全部条目 JSON 数组（json.dumps，取前 20 条、与 item 槽同源；空文本/解析失败=空串），
  可一根线直连 资产提示词批量生成 / 三视图提示词批量生成 的合并输入（免去 20 路手接），
  或连 LLM 对话整批审改 / 存档

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
> ② 拆分 `第 N 条` → `Agnes 资产提示词生成`（subject_type=角色，style 自选；
> 20 条并发生成请改接 `Agnes 资产提示词批量生成`，见其独立章节）
> ③ `英文资产生成提示词` → `Agnes 图像生成`（n=1，或 三视图提示词生成 → 三视图生成 subject_desc，
>    想系列一致再 reference_image 接一张已出图）
> 场景/道具/服装走同一条链，换 subject_type 即可
> 批量省调用：也可用 LLM 对话一次把整份 JSON 转成【名】英文提示词，
> 再接 文本拆分(【】括号块模式) 扇出（少 19 次 LLM 调用）

---

### 🖌️ Agnes 资产提示词批量生成 (AgnesAssetPromptBatch)

**功能：** 资产 JSON 合并输入驱动的批量资产提示词生成节点：
1 路 all_items 全文合并输入（↔ 文本拆分 all_items 输出 / 资产提取 5 路 JSON，
JSON 数组可一根线直连，免 20 路手接；也接受单条资产 JSON 纯文本，视为 1 条），
线程池并发生成英文生图提示词，`max_concurrency` 限制同时请求数（默认 10，
超出排队执行），20 路 english_prompt + status + all_prompts 输出。
参数与单条「Agnes 资产提示词生成」完全一致，整批共用。
all_items 空项=跳过该槽（槽号保位，与旧 20 槽行为一致）；单槽失败不影响其他槽。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all_items | STRING(多行) | "" | 资产 JSON 合并输入：① JSON 数组（资产提取 5 路 JSON / 文本拆分 all_items 直连，条目从上到下逐条生成，最多 20 条超出截断，空项=跳过该槽槽号保位）② 单条资产 JSON 纯文本（连 文本拆分 item_i 或粘贴，视为 1 条）③ 空=整批跳过（零 API 调用） |
| subject_type | COMBO | 角色 | 角色/物品道具/服装/场景/载具/通用（整批共用，决定构图指令） |
| style | COMBO | cinematic | 生图风格尾词（整批共用）：cinematic/anime/realistic/watercolor/oil_painting |
| base_url | STRING | （留空=跟随全局） | 请求地址 Base URL，可动态覆盖 |
| api_key | STRING | 留空自动加载 | Agnes AI API Key |
| model | COMBO | agnes-2.5-flash | 文本生成模型（整批共用） |
| reasoning_effort | COMBO | auto | 思考等级（整批共用） |
| max_concurrency | INT | 10 | 并发速率限制（线程池大小，1-20）：非空资产 JSON 超过该值时排队；频繁 429/503 就调小 |

**输出（22 路）：**
- english_prompt_1..english_prompt_20：各槽（all_items 第 i 条）英文资产生图提示词（保留 JSON 全部描述字段 + 构图指令 + 风格/质量尾词），
  可直接接 图像生成 / 三视图生成(subject_desc)；空输入=空字符串；失败=`[Error]` 前缀文本
- status：整批执行状态 JSON `{"success":[成功槽号],"error":[失败槽号，含空响应],"empty":[空输入槽号]}`（**槽号=all_items 条目序号，1 起保位**）；
  全部请求失败（success 为空且 error 非空）时额外含 `"reason"` 字段——各槽同一原因=字符串，不同=槽号→原因映射；
  可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，
  或接 LLM 对话让模型解读哪些槽需要重试（空响应=API 200 但正文为空，常见为思考预算耗尽：降 reasoning_effort / 换 agnes-2.5-flash）
- all_prompts：本批成功生成的英文提示词 JSON 数组（ensure_ascii=False，按槽号升序；失败/空槽不含；全空/缺 Key/零成功=空串），
  可一根线直连 Agnes 三视图提示词批量生成 all_prompts 输入（批量出三视图提示词）

> 典型接法（资产线批量，一根线到底）：
> `资产提取.角色JSON（JSON 数组，直连）→ 资产提示词批量生成(all_items) → all_prompts → 三视图提示词批量生成(all_prompts) → all_turnaround_prompts → 三视图批量生成(all_prompts) → all_images → 图像拼图(batch_images)`
> 或 `文本拆分.all_items（LLM 扩写后的条目）→ 本节点`；轻量单槽：`文本拆分 item_i 单条纯文本 → all_items`（视为 1 条）。
> 日志：`[Agnes 资产提示词批量] 输入=JSON 数组，条目 N（超 20 条已截断），非空 M 条，并发 K`，每槽完成打印 `#i 成功 N 字 预览...` / `#i 失败 原因`，收尾打印 `完成：成功 X/N` + `状态: success=[…] error=[…] empty=[…]` + `all_prompts: N 条成功提示词 → JSON 输出`。
> 旧实例（27 槽结构）载入时 web/js/agnes-migrate.js 自动迁移 widget 值（27→8），无需手工重建。

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
   - 多视频异步接法（推荐）：「Agnes 视频任务提交」秒级提交拿 task_url（画布立刻解放）→
     收取两种接法任选：
     a. 「Agnes 视频任务收取」单任务实例：一任务一实例，稍后右键运行收片
     （自动下载 output/agnes_videos/，多实例分波放置，出片期间画布空闲）；
     b. 「Agnes 视频任务批量收取」：提交实例的 task_url_key 输出 直连 task_1…task_20
     （每波 20 实例 ↔ 1 个批量收取实例，0 中间节点，各槽 Key 可全不同），
     线程池并发收取，单节点收完一波 20 镜（总时长≈max 而非 sum，免逐任务右键）
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
- 调低 seconds 时长（如 12→5 秒）或调大 max_wait_seconds
- 异步两段式：收取 节点到轮询超时未完成（不算任务失败）：原生视频环境=节点出 NO_VIDEO_ 黑帧占位 + status 输出 processing（文案指引「再次运行本节点继续查询」），VHS/STRING 环境=status 输出 processing → 再次右键运行该节点即继续查（任务还在服务端，不重复计费）
- 稍后重试（服务器可能繁忙）

### 视频队列已满（503 video_queue_full）
- 提交任务时服务端返回 503「视频队列已满」：客户端自动退避重试，次数由节点「重试次数」参数
  （retries）控制，默认 5 次：固定 30 秒/次（累计 150 秒/2.5 分钟，
  睡眠带 ±15% 随机抖动错峰；参数 0=不重试；上限 120 次累计 3600 秒/60 分钟（视频任务提交），文生视频等为 30 次累计 900 秒/15 分钟；
  503 响应带 Retry-After 头时优先按服务端指定秒数）
- 报错后请等 5-10 分钟（视频与生图队列相互独立，互不影响）再运行本节点
- 高峰期（晚间 20-24 点）队列最忙，可错峰生成

### 视频文件下载失败（生成已成功）
- 报错格式：「[Video 错误] 视频文件下载失败（已自动重试 3 次，<诊断>）」，
  并附 `video_url`、`task_id`、`video_id`——服务端已渲染完成，只差把文件拉回本机
- 客户端已自动重试 3 次（2/5/10 秒），仍失败多为瞬时网络/代理问题
- 抢救：若 `video_url` 仍在有效期内，用浏览器打开该 URL 手动下载（可换直连/代理试试）
- 诊断含义：`HTTP 403/404`=链接失效或已过期；`HTTP 401`=鉴权问题；
  `ConnectionError`/`Timeout`=到 CDN 网络不通（检查代理是否拦截了视频 CDN 域名）
- 无法抢救时重跑本节点即可（重新生成）

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
