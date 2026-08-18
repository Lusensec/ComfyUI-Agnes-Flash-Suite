"""
Agnes 剧本生成节点
使用 Agnes LLM 生成影视解说文案
"""
import requests
import re
from ..api import AgnesClient, BASE_URL, CHAT_MODEL


class AgnesScriptGenerator:
    """使用 Agnes LLM 生成解说文案"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "story_outline": ("STRING", {
                    "multiline": True,
                    "default": ""
                }),
                "api_key": ("STRING", {
                    "default": "sk-你的Key",
                    "placeholder": "Agnes API Key"
                }),
                "style": (["casual", "professional", "humorous", "dramatic"], {"default": "casual"}),
                "target_duration": ("INT", {"default": 180, "min": 60, "max": 600}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.05}),
            },
            "optional": {
                "base_url": ("STRING", {"default": BASE_URL}),
                "model": ("STRING", {"default": CHAT_MODEL}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("script",)
    FUNCTION = "generate"
    CATEGORY = "🎬 Agnes Novel"

    def generate(self, story_outline, api_key, style, target_duration, temperature, base_url=BASE_URL, model=CHAT_MODEL):
        if not api_key:
            raise ValueError("Agnes API Key required")

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

        print(f"[Agnes Script] Generating script (target: {target_chars} chars)...")

        try:
            client = AgnesClient(api_key)
            script = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                max_tokens=target_chars * 2,
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
            raise


NODE_CLASS_MAPPINGS = {"AgnesScriptGenerator": AgnesScriptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScriptGenerator": "📝 Agnes 剧本生成"}
