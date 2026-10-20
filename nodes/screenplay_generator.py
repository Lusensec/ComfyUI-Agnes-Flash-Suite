"""
Agnes 剧本生成节点（漫剧短视频）
=================
使用 Agnes LLM 把故事大纲改写成「漫剧短视频分场剧本」：
核心钩子 + 分场三行结构（画面/对白/氛围），画面描述具象可视，
可直接接 场景切分 → 分镜提示词生成 → 图像生成 → 关键帧生视频 管线，
也可人工修改后作为漫剧/短剧的分镜脚本。

与「Agnes 解说剧本生成（AgnesScriptGenerator）」的区别：
  - 解说剧本生成 = 口播解说稿（配音轨，对观众的叙述腔）
  - 本节点       = 分场剧本（画面+对白+氛围，漫剧结构）

漫剧类型（style）：逆袭爽文 / 甜宠治愈 / 悬疑惊悚 / 搞笑沙雕 / 热血冒险 / 虐心催泪。
"""

import re
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort


class AgnesScreenplayGenerator:
    """使用 Agnes LLM 生成漫剧短视频分场剧本"""

    DESCRIPTION = "根据故事大纲生成漫剧短视频分场剧本（核心钩子+画面/对白/氛围），支持 6 种漫剧类型"

    STYLE_MAP = {
        "逆袭爽文": "逆袭爽文：快节奏爽点密集、反转打脸、主角逆袭翻盘",
        "甜宠治愈": "甜宠治愈：温馨治愈基调、CP 互动自然、暖系台词与治愈名场面",
        "悬疑惊悚": "悬疑惊悚：氛围感拉满、层层悬念钩子、反转惊悚、结尾留悬念",
        "搞笑沙雕": "搞笑沙雕：笑点密集、梗多语快、沙雕名场面、节奏轻快",
        "热血冒险": "热血冒险：动作场面多、成长线清晰、高燃高潮、热血台词",
        "虐心催泪": "虐心催泪：情感张力强、虐点精准、泪点催泪、共情名场面",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "story_outline": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事大纲或章节摘要...",
                    "tooltip": "故事大纲，用于生成漫剧剧本"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key"
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）"
                }),
                "style": (list(cls.STYLE_MAP.keys()), {
                    "default": "逆袭爽文",
                    "tooltip": "漫剧类型：逆袭爽文/甜宠治愈/悬疑惊悚/搞笑沙雕/热血冒险/虐心催泪"
                }),
                "target_duration": ("INT", {
                    "default": 180,
                    "min": 60,
                    "max": 600,
                    "tooltip": "目标总时长（秒），按每场 5–15 秒估算场次"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "生成温度，越高越有创意，越低越稳定"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
                }),
            },
            "optional": {
                "characters": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "每行一个角色：名字 + 一句人设，如「团团：胖橘猫，傲娇贪吃」「张大婶：热心洗衣大婶」",
                    "tooltip": "可选：角色列表（每行一个，名字+一句人设），让剧本对白/动作保持角色一致"
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("script",)
    RETURN_LABELS = ("漫剧剧本",)
    OUTPUT_TOOLTIPS = ("漫剧短视频分场剧本（核心钩子+分场三行结构：画面/对白/氛围）；可接 场景切分/分镜提示词生成 继续管线，或接 SaveText 存档",)
    FUNCTION = "generate"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "script" in kwargs:
            extra["script"] = {
                "description": "漫剧短视频分场剧本，含核心钩子与分场画面/对白/氛围结构"
            }
        return extra

    def generate(self, story_outline="", base_url="", api_key="", style="逆袭爽文", target_duration=180, temperature=0.8, model=CHAT_MODEL, reasoning_effort="auto", characters=""):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）",)

        target_scenes = max(3, round(target_duration / 8))
        characters_block = f"\n角色设定（剧本中的对白/动作请保持这些角色一致）：\n{characters}\n" if characters.strip() else ""

        prompt = f"""你是一位专业的漫剧短视频编剧，擅长把故事大纲改写成适合 AI 漫剧（动态漫画短剧）的分场剧本：节奏快、画面感强、每场都能直接转成画面与镜头。请根据以下故事大纲创作剧本。

剧本类型：{self.STYLE_MAP[style]}

故事大纲：
{story_outline}
{characters_block}
【剧本格式】
1. 剧本第一行写「核心钩子」：一句话点出全剧最抓人的悬念/爽点/情绪点
2. 然后分场写作，每场严格三行、各占一行：
   场景一：DAY 河畔石池
   画面：（景别+镜头内容+角色动作表情，如「全景：薄雾小镇河边，团团蹲在石池边拨水够银鲤」）
   对白：（格式「角色名：台词」，可多句；无台词写「对白：无」）
   氛围：（一句情绪/音效设计，如「水花声+远处市井人声」）
3. 场景编号用中文数字（场景一、场景二……），场景行写 时间(DAY/NIGHT)+地点
4. 每场 5–15 秒，全剧共 {target_scenes} 场左右，总时长约 {target_duration} 秒

【节奏与结构】
- 钩子开场（前 3 场必须抓人）→ 冲突发展（反转/升级）→ 高潮收束 → 结尾留钩（为下一集埋悬念）
- 对白短促、有角色感，可设计口头禅；动作描写具象可视（不写「心里难受」，写「手指攥紧衣角，指节发白」）

【禁止事项】
- 不要解说腔：禁止「你想想」「你看」「别划走」等对观众的口播话术
- 不要用【】等标记符号，不要「第一、第二」列表式结构
- 不要总结性废话，直接输出剧本："""

        print(f"[Agnes 漫剧剧本] 生成 {style} 类型分场剧本（约 {target_scenes} 场 / {target_duration} 秒），思考等级={normalize_reasoning_effort(reasoning_effort) or '默认'}...")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            script = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                max_tokens=target_scenes * 200,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
            )

            # 清理（与 解说剧本生成 一致的兜底）
            script = re.sub(r'【[^】]*】', '', script)
            script = re.sub(r'\[[^\]]*\]', '', script)
            script = re.sub(r'\n{3,}', '\n\n', script)
            script = script.strip()

            print(f"[Agnes Screenplay] Generated {len(script)} chars")
            return (script,)

        except Exception as e:
            print(f"[Agnes Screenplay] Failed: {e}")
            return (f"[Error] {str(e)}",)


NODE_CLASS_MAPPINGS = {"AgnesScreenplayGenerator": AgnesScreenplayGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScreenplayGenerator": "🎭 Agnes 剧本生成"}
