"""
Agnes 场景拆分节点
将故事文本（小说章节 或 漫剧/解说剧本）拆分为 5 秒/片的场景段落
"""
import requests
import json
import re
import os
import time
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, VIDEO_MAX_WAIT, VIDEO_POLL_INTERVAL, format_chat_meta, FOLLOW_GLOBAL, resolve_chat_params


MAX_SLOTS = 60


class AgnesSceneSplitter:
    """
    Agnes 场景拆分 v33
    使用 agnes-2.5-flash 进行场景切分
    """
    
    DESCRIPTION = "将故事文本（小说章节 或 漫剧剧本）切分为多个场景段落，每个段落约对应 5 秒视频内容，包含角色、动作、场景标注"

    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事文本（小说章节全文，或 漫剧/解说 剧本全文）...\n建议 3000-8000 字",
                    "tooltip": "待处理的故事文本：小说章节全文，或 漫剧剧本（场景行/画面/对白/氛围 四行结构，各场景行=天然场景边界，直接切分）/解说文案；单份建议 3000-8000 字"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key，从 https://platform.agnes-ai.com 获取"
                }),
                "model": (AVAILABLE_CHAT_MODELS + [FOLLOW_GLOBAL], {
                    "default": FOLLOW_GLOBAL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）；选「跟随全局（默认）」= 解析「Agnes API Key 配置」的全局对话模型（未配置则回落 2.5-flash）"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效；auto/空 = 跟随全局（Key 配置节点设置时），否则跟随模型默认"
                }),
            },
            "optional": {
                "retries": ("INT", {
                    "label": "重试次数",
                    "default": 3,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "tooltip": "失败重试次数（0=不重试，请求一次即止）：429 限流/5xx 服务端错误自动退避重试（3/6/12s…），默认 3；最坏总时长≈(1+重试次数)×请求超时",
                }),
                "timeout": ("INT", {
                    "label": "请求超时（秒）",
                    "default": 300,
                    "min": 30,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "单次 API 调用等待上限（秒），默认 300：长思考模式（thinking 高档位）/长上下文可拉高到 3600",
                }),
            }
        }
        return inputs

    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 6)
    RETURN_NAMES = ("log_text",) + tuple(f"scene_{i}" for i in range(1, MAX_SLOTS + 1)) + (
        "chapter_text_out", "api_key_out", "base_url_out", "model_out",
        "all_scenes",
    )
    RETURN_LABELS = ("处理日志",) + tuple(f"场景 {i}" for i in range(1, MAX_SLOTS + 1)) + (
        "原文本（透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）",
        "场景全文（JSON 数组）",
    )
    OUTPUT_TOOLTIPS = ("处理日志（场景统计/响应元数据/空响应警示/错误详情）",) + (
        ("5 秒场景片段（原文切段，连接总导演或提示词节点）",) * MAX_SLOTS
    ) + ("原始故事文本（小说章节/剧本，透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）",
         f"{MAX_SLOTS} 个场景段落按序合并为 JSON 数组（跳过空槽）；可直连 分镜提示词批量生成 all_scenes 输入 / 总导演 单路输入 / LLM 对话 / 存档")
    FUNCTION = "split_scenes"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        outputs = {
            "log_text": "处理日志，包含成功/失败信息、响应元数据（finish_reason/token 消耗）、空响应警示和输出文件路径",
            "scene_1": "第 1 个场景段落",
            "scene_2": "第 2 个场景段落",
            "scene_3": "第 3 个场景段落",
            "scene_4": "第 4 个场景段落",
            "scene_5": "第 5 个场景段落",
        }
        for i in range(6, MAX_SLOTS + 1):
            outputs[f"scene_{i}"] = f"第 {i} 个场景段落（如果存在）"
        outputs["chapter_text_out"] = "原始故事文本（小说章节/剧本，透传）"
        outputs["api_key_out"] = "API Key（透传）"
        outputs["base_url_out"] = "API 地址（透传）"
        outputs["model_out"] = "使用的模型名称（透传）"
        outputs["all_scenes"] = f"{MAX_SLOTS} 个场景段落按序合并为 JSON 数组（跳过空槽）；可直连 分镜提示词批量生成 / LLM 对话 / 存档"
        
        for key in outputs:
            if key in kwargs:
                extra[key] = {"description": outputs[key]}
        return extra

    def split_scenes(self, chapter_text="", base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto", retries=3, timeout=300):
        chapter_text = (chapter_text or "").strip()
        if not chapter_text:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 文本输入 / Agnes 剧本生成 / Agnes 解说剧本生成 的文本输出，或直接粘贴小说章节 / 剧本全文"
            print(f"[Agnes 场景拆分] {skip_msg}")
            result = [skip_msg] + [""] * MAX_SLOTS + ["", api_key, base_url, model, ""]
            return tuple(result)
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            error_msg = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            result = [error_msg] + [""] * MAX_SLOTS + [chapter_text, api_key, base_url, model, ""]
            return tuple(result)
        print(f"\n{'='*60}")
        print(f"[Agnes 场景拆分 - {model}]")
        print(f"{'='*60}")

        prompt = f"""你是一位专业的影视剪辑师。请将以下故事文本（小说章节 或 剧本）切分成段落，每个段落对应5秒视频能容纳的内容。

【剧本输入处理】（输入为 场景行/画面/对白/氛围 结构的剧本时）
• 每个场景行（如"场景一：DAY 小镇池塘石沿"）是天然场景边界，必须在此处切分，禁止跨场景行合并
• "画面"描述按动作粒度切段；"对白"行原样归入对应段落（【角色】【性别】标签取自对白说话人与画面角色）
• "氛围"中的镜头/音效设计随所属段落保留

【核心规则】

一、切分粒度
• 每个段落 = 约5秒视频 = 大概3-5个简单动作 + 1个固定场景
• 如果一个自然段包含多于一个5秒视频能包含的动作，必须切成多个段落
• 严禁超出五秒钟视频能包含的内容范围
• 禁止裁剪无故事情节，无意义片段
• 禁止相邻两个片段过度雷同
• 每个片段必须包含具体动作词，如无动作词，则适当增加段落长度以包含必要的动作词
• 如果原文明确描述了场景切换（如"走出房间""来到雪山"），必须单独切出3-5个"过渡"段落

【动作定义扩展】
"单动作"不仅指物理动作，也包括情感动作。
一个完整的情感表达（如"赞美女主"）可以包含：
- 眼神变化（从注意到欣赏）
- 微表情（嘴角上扬、眉梢舒展）
- 身体微倾（不自觉地靠近）
- 一个完整的情绪弧线

禁止把情感表达切成碎片。
如果一个段落的核心是情感表达，整个情感过程算一个分镜。

二、场景切换检测【极其重要 - 严格遵循】

触发条件（只有以下情况才需要切场景）：
• 原文明确描述了从一个地点移动到另一个地点（如"走进山洞"、"回到屋内"）
• 原文明确描述了环境的本质变化（如"天黑了"、"暴风雪来了"）
• 不触发切换的情况：同一场景内的视角移动、人物走动、细节观察

切换规则（每次场景切换必须包含3-5个过渡分镜）：
• 第1镜：远景/全景 — 展示新场景的全貌（如"远处出现一座木屋"）
• 第2镜：中景 — 人物向新场景移动（如"大家向木屋走去"）
• 第3镜：近景 — 人物到达新场景入口（如"站在木屋门前"）
• 第4镜：动作 — 人物进入新场景（如"推开门走进屋内"）
• 第5镜：特写/中景 — 在新场景内的第一个动作（如"在温暖的壁炉前坐下"）

每个过渡分镜以 [TRANSITION] 标记，并按上述顺序排列。
禁止只用一个分镜完成场景切换。

三、输出要求
• 每个段落用原文的核心描述，保留原文的关键名词和动词
• 每个段落必须包含：谁、角色名字、性别、在哪、做什么
• 不添加分镜术语、不添加运镜描述、不生成提示词
• 段落之间用换行分隔
• 不限段落数量，根据内容自动决定

【输出格式 - 纯文本】
[SCENE_1]
【角色A】【男】【角色B】【女】【角色C】【男】……(原文段落1的核心描述)

[SCENE_2]
【角色B】【男】【角色C】【女】……(原文段落2的核心描述)

[TRANSITION] (如果有场景切换)
(过渡段落描述)

[SCENE_3]
【角色A】【男】【角色C】【女】……(原文段落3的核心描述)

... 继续直到内容结束 ...

【故事文本（小说章节 或 剧本）】
{chapter_text}"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            model, _tv, reasoning_effort = resolve_chat_params(model, reasoning_effort=reasoning_effort)
            content, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.2,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
                retries=retries,
                timeout=timeout,
            )

            scenes = self._parse_scenes(content or "")

            # 保存到输出目录
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "AgnesOutput")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            script_path = os.path.join(output_dir, f"storyboard_agnes_{timestamp}.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(content or "")

            meta_line = format_chat_meta(meta)
            if not (content or "").strip():
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试（0 个段落）")
            else:
                log = f"✅ Agnes 切段完成: {len(scenes)} 个段落\n· 响应元数据：{meta_line}\n📋 脚本: {script_path}"
            print(log)

            result = [log]
            for i in range(1, MAX_SLOTS + 1):
                result.append(scenes.get(i, ""))
            result.append(chapter_text)
            result.append(api_key)
            result.append(base_url)
            result.append(model)
            # all_scenes：60 个场景段落按序合并为 JSON 数组（跳过空槽），
            # 供直连「Agnes 分镜提示词批量生成」all_scenes 输入 / 总导演 单路输入 / LLM 对话 / 存档
            all_scenes = json.dumps([x for x in result[1:MAX_SLOTS + 1] if x.strip()], ensure_ascii=False, indent=2)
            result.append(all_scenes)

            return tuple(result)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = (f"❌ Agnes 切段失败（{type(e).__name__}）: {e}\n"
                         f"· 请求参数: model={model}；reasoning_effort={reasoning_effort}\n"
                         f"── 完整堆栈 ──\n{tb}")
            print(error_msg)
            result = [error_msg] + [""] * MAX_SLOTS + [chapter_text, api_key, base_url, model, ""]
            return tuple(result)

    def _parse_scenes(self, content):
        """解析 [SCENE_n] / [TRANSITION] 块。

        场景按模型给出的编号存入对应槽位；过渡段 [TRANSITION] 统一追加到
        「最大场景编号之后」的槽位，避免被随后同编号的 [SCENE_n] 块覆盖丢失。
        """
        scenes = {}
        transitions = []
        blocks = re.split(r'\[(SCENE_\d+|TRANSITION)\]', content)
        for i in range(1, len(blocks), 2):
            tag = blocks[i]
            text = blocks[i+1].strip() if i+1 < len(blocks) else ""
            if tag.startswith("SCENE_"):
                num = int(re.search(r'\d+', tag).group())
                scenes[num] = text
            elif tag == "TRANSITION":
                transitions.append(text)
        # 过渡段排在所有场景之后
        base = max(scenes.keys()) if scenes else 0
        for i, t in enumerate(transitions, 1):
            scenes[base + i] = f"[TRANSITION] {t}"
        return scenes


NODE_CLASS_MAPPINGS = {"AgnesSceneSplitter": AgnesSceneSplitter}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesSceneSplitter": "🎬 Agnes 场景切分"}
