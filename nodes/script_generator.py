"""
Agnes 剧本生成节点
使用 Agnes LLM 生成影视解说文案
"""
import requests
import re
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort


class AgnesScriptGenerator:
    """使用 Agnes LLM 生成解说文案"""
    
    DESCRIPTION = "根据故事大纲生成影视解说文案，支持多种风格和时长"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "story_outline": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事大纲或章节摘要...",
                    "tooltip": "故事大纲，用于生成解说文案"
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
                "style": (["casual", "professional", "humorous", "dramatic"], {
                    "default": "casual",
                    "tooltip": "解说风格：casual=风趣幽默，professional=深度解读，humorous=轻松搞笑，dramatic=情感饱满"
                }),
                "target_duration": ("INT", {
                    "default": 180,
                    "min": 60,
                    "max": 600,
                    "tooltip": "目标时长（秒），约等于文案字数/5"
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
            "optional": {}
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("script",)
    RETURN_LABELS = ("解说文案")
    OUTPUT_TOOLTIPS = ("影视解说文案（含开场/讲解/结尾完整结构，连接 SaveText 或作为配音稿）",)
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
                "description": "影视解说文案，包含开场、讲解、结尾等完整内容"
            }
        return extra

    def generate(self, story_outline="", base_url="", api_key="", style="casual", target_duration=180, temperature=0.8, model=CHAT_MODEL, reasoning_effort="auto"):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]",)

        target_chars = target_duration * 5

        style_map = {
            "casual": "风趣幽默、接地气，像朋友聊天一样自然",
            "professional": "深度解读，有思考和见解",
            "humorous": "轻松搞笑，节奏快，抓重点",
            "dramatic": "情感饱满，有张力，引人入胜"
        }

        prompt = f"""你是一位百万粉丝的影视解说博主，擅长把电视剧讲得比原片还精彩。请根据以下故事大纲创作解说文案。

风格要求：{style_map[style]}

故事大纲：
{story_outline}

【写作要求】
1. 字数：约{target_chars}字，必须完整讲完一集全部内容
2. 开场要抓人：像"兄弟们这集绝了"、"来了来了"这种，一秒抓住观众
3. 讲解要有视角：站在观众角度讲故事，不是冷冰冰复述剧情
4. 适当发挥：在关键情节加入吐槽、联想、感慨，让文案有"人味儿"
5. 段落要顺滑：段与段之间自然过渡
6. 结尾要有力：总结观点或留下悬念
7. 语言要自然：像在和朋友聊天，多用"你想想"、"这不就"这类口语

【禁止事项】
- 不要用【】、[]等任何标记符号
- 不要出现"第一、第二、第三"这种列表式结构
- 不要写"以上是..."这类总结性废话
- 不要重复同样的句式

请直接输出解说文案，不要有任何额外说明："""

        print(f"[Agnes Script] Generating script (target: {target_chars} chars), thinking={normalize_reasoning_effort(reasoning_effort) or 'default'}...")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            script = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                max_tokens=target_chars * 2,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
            )

            # 清理
            script = re.sub(r'【[^】]*】', '', script)
            script = re.sub(r'\[[^\]]*\]', '', script)
            script = re.sub(r'\n{3,}', '\n\n', script)
            script = script.strip()

            print(f"[Agnes Script] Generated {len(script)} chars")
            return (script,)

        except Exception as e:
            print(f"[Agnes Script] Failed: {e}")
            return (f"[Error] {str(e)}",)


NODE_CLASS_MAPPINGS = {"AgnesScriptGenerator": AgnesScriptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScriptGenerator": "Agnes 剧本生成"}
