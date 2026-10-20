"""
Agnes 剧本生成节点
使用 Agnes LLM 生成影视解说文案
"""
import requests
import re
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta


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

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("script", "log_text")
    RETURN_LABELS = ("解说文案", "响应日志")
    OUTPUT_TOOLTIPS = ("影视解说文案（含开场/讲解/结尾完整结构，连接 SaveText 或作为配音稿）",
                       "响应日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常详情），方便定位空正文/截断问题")
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
        if "log_text" in kwargs:
            extra["log_text"] = {
                "description": "响应日志（响应元数据/空响应警示/异常详情）"
            }
        return extra

    def generate(self, story_outline="", base_url="", api_key="", style="casual", target_duration=180, temperature=0.8, model=CHAT_MODEL, reasoning_effort="auto"):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）", "API Key 缺失。")

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

        print(f"[Agnes 剧本] 生成解说文案（目标 {target_chars} 字），思考等级={normalize_reasoning_effort(reasoning_effort) or '默认'}...")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )

            # 清理
            script = re.sub(r'【[^】]*】', '', raw)
            script = re.sub(r'\[[^\]]*\]', '', script)
            script = re.sub(r'\n{3,}', '\n\n', script)
            script = script.strip()

            meta_line = format_chat_meta(meta)
            if not script:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试")
                print(f"[Agnes Script] 空响应（0 字）")
                return ("", log)

            log = (f"✅ 生成完成（{len(script)} 字）\n"
                   f"· 响应元数据：{meta_line}")
            print(f"[Agnes Script] Generated {len(script)} chars")
            return (script, log)

        except Exception as e:
            print(f"[Agnes Script] Failed: {e}")
            tb = traceback.format_exc()
            log = f"❌ API 调用失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            return (f"[Error] {str(e)}", log)


NODE_CLASS_MAPPINGS = {"AgnesScriptGenerator": AgnesScriptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScriptGenerator": "📝 Agnes 解说剧本生成"}
