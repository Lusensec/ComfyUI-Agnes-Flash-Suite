"""
Agnes 场景拆分节点
将小说章节拆分为 5 秒/片的场景段落
"""
import requests
import json
import re
import os
import time
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, VIDEO_MAX_WAIT, VIDEO_POLL_INTERVAL, format_chat_meta


class AgnesSceneSplitter:
    """
    Agnes 场景拆分 v32
    使用 agnes-2.5-flash 进行场景切分
    """
    
    DESCRIPTION = "将小说章节切分为多个场景段落，每个段落约对应 5 秒视频内容，包含角色、动作、场景标注"

    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入小说章节全文...\n建议 3000-8000 字",
                    "tooltip": "待处理的小说章节文本，单章建议 3000-8000 字"
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
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
                }),
                "max_tokens": ("INT", {
                    "default": 12000,
                    "min": 2000,
                    "max": 16000,
                    "step": 1000,
                    "tooltip": "输出 token 预算：切分长章节需要大预算；思考模型（reasoning_effort≥medium）下建议拉满 16000 防空正文"
                }),
            }
        }
        return inputs

    RETURN_TYPES = ("STRING",) * 55
    RETURN_NAMES = (
        "log_text",
        "scene_1", "scene_2", "scene_3", "scene_4", "scene_5",
        "scene_6", "scene_7", "scene_8", "scene_9", "scene_10",
        "scene_11", "scene_12", "scene_13", "scene_14", "scene_15",
        "scene_16", "scene_17", "scene_18", "scene_19", "scene_20",
        "scene_21", "scene_22", "scene_23", "scene_24", "scene_25",
        "scene_26", "scene_27", "scene_28", "scene_29", "scene_30",
        "scene_31", "scene_32", "scene_33", "scene_34", "scene_35",
        "scene_36", "scene_37", "scene_38", "scene_39", "scene_40",
        "scene_41", "scene_42", "scene_43", "scene_44", "scene_45",
        "scene_46", "scene_47", "scene_48", "scene_49", "scene_50",
        "chapter_text_out", "api_key_out", "base_url_out", "model_out",
    )
    RETURN_LABELS = (
        "处理日志",
        "场景 1", "场景 2", "场景 3", "场景 4", "场景 5",
        "场景 6", "场景 7", "场景 8", "场景 9", "场景 10",
        "场景 11", "场景 12", "场景 13", "场景 14", "场景 15",
        "场景 16", "场景 17", "场景 18", "场景 19", "场景 20",
        "场景 21", "场景 22", "场景 23", "场景 24", "场景 25",
        "场景 26", "场景 27", "场景 28", "场景 29", "场景 30",
        "场景 31", "场景 32", "场景 33", "场景 34", "场景 35",
        "场景 36", "场景 37", "场景 38", "场景 39", "场景 40",
        "场景 41", "场景 42", "场景 43", "场景 44", "场景 45",
        "场景 46", "场景 47", "场景 48", "场景 49", "场景 50",
        "原文本（透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）",
    )
    OUTPUT_TOOLTIPS = ("处理日志（场景统计/响应元数据/空响应警示/错误详情）",) + (
        ("5 秒场景片段（原文切段，连接总导演或提示词节点）",) * 50
    ) + ("小说原文本（透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）")
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
        for i in range(1, 51):
            outputs[f"scene_{i}"] = f"第 {i} 个场景段落（如果存在）"
        outputs["chapter_text_out"] = "原始小说章节文本（透传）"
        outputs["api_key_out"] = "API Key（透传）"
        outputs["base_url_out"] = "API 地址（透传）"
        outputs["model_out"] = "使用的模型名称（透传）"
        
        for key in outputs:
            if key in kwargs:
                extra[key] = {"description": outputs[key]}
        return extra

    def split_scenes(self, chapter_text="", base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto", max_tokens=12000):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            error_msg = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            result = [error_msg] + [""] * 50 + [chapter_text, api_key, base_url, model]
            return tuple(result)
        print(f"\n{'='*60}")
        print(f"[Agnes 场景拆分 - {model}]")
        print(f"{'='*60}")

        prompt = f"""你是一位专业的影视剪辑师。请将以下小说章节切分成段落，每个段落对应5秒视频能容纳的内容。

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

【小说章节】
{chapter_text}"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            content, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.2,
                max_tokens=max_tokens,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )

            scenes = self._parse_scenes(content or "")

            # 保存到输出目录
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "AgnesOutput")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            script_path = os.path.join(output_dir, f"storyboard_agnes_{timestamp}.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(content or "")

            meta_line = format_chat_meta(meta, max_tokens)
            if not (content or "").strip():
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级或调大 max_tokens 后重试（0 个段落）")
            else:
                log = f"✅ Agnes 切段完成: {len(scenes)} 个段落\n· 响应元数据：{meta_line}\n📋 脚本: {script_path}"
            print(log)

            result = [log]
            for i in range(1, 51):
                result.append(scenes.get(i, ""))
            result.append(chapter_text)
            result.append(api_key)
            result.append(base_url)
            result.append(model)

            return tuple(result)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = (f"❌ Agnes 切段失败（{type(e).__name__}）: {e}\n"
                         f"· 请求参数: model={model}；max_tokens={max_tokens}\n"
                         f"── 完整堆栈 ──\n{tb}")
            print(error_msg)
            result = [error_msg] + [""] * 50 + [chapter_text, api_key, base_url, model]
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
