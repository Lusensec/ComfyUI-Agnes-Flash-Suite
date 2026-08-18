"""
Agnes 场景拆分节点
将小说章节拆分为 5 秒/片的场景段落
"""
import requests
import json
import re
import os
import time
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, VIDEO_MAX_WAIT, VIDEO_POLL_INTERVAL


class AgnesSceneSplitter:
    """
    Agnes 场景拆分 v32
    使用 agnes-2.5-flash 进行场景切分
    """

    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入小说章节全文..."
                }),
                "api_key": ("STRING", {
                    "default": "sk-你的Key",
                    "placeholder": "Agnes API Key"
                }),
            },
            "optional": {
                "base_url": ("STRING", {
                    "default": BASE_URL
                }),
                "model": ("STRING", {
                    "default": CHAT_MODEL
                }),
            }
        }
        return inputs

    RETURN_TYPES = (
        "STRING",) * 55  # log + 50 scenes + 4 pass-through
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
    FUNCTION = "split_scenes"
    CATEGORY = "🎬 Agnes Novel"

    def split_scenes(self, chapter_text, api_key, base_url=BASE_URL, model=CHAT_MODEL):
        print(f"\n{'='*60}")
        print(f"[Agnes Scene Splitter - {model}]")
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
            client = AgnesClient(api_key)
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.2,
                max_tokens=12000,
            )

            scenes = self._parse_scenes(content)

            # 保存到输出目录
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "AgnesOutput")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            script_path = os.path.join(output_dir, f"storyboard_agnes_{timestamp}.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(content)

            log = f"✅ Agnes 切段完成: {len(scenes)} 个段落\n📋 脚本: {script_path}"
            print(log)

            result = [log]
            for i in range(1, 51):
                result.append(scenes[i] if i <= len(scenes) else "")
            result.append(chapter_text)
            result.append(api_key)
            result.append(base_url)
            result.append(model)

            return tuple(result)

        except Exception as e:
            error_msg = f"❌ Agnes 切段失败: {e}"
            print(error_msg)
            result = [error_msg] + [""] * 50 + [chapter_text, api_key, base_url, model]
            return tuple(result)

    def _parse_scenes(self, content):
        scenes = {}
        blocks = re.split(r'\[(SCENE_\d+|TRANSITION)\]', content)
        current_num = 0
        for i in range(1, len(blocks), 2):
            tag = blocks[i]
            text = blocks[i+1].strip() if i+1 < len(blocks) else ""
            if tag.startswith("SCENE_"):
                current_num = int(re.search(r'\d+', tag).group())
                scenes[current_num] = text
            elif tag == "TRANSITION":
                current_num += 1
                scenes[current_num] = "[TRANSITION] " + text
        return scenes


NODE_CLASS_MAPPINGS = {"AgnesSceneSplitter": AgnesSceneSplitter}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesSceneSplitter": "🎬 Agnes 场景切分"}
