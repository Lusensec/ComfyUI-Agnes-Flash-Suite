"""
Agnes 分镜提示词生成节点
将分镜脚本转换为 Agnes Image API 可用的详细提示词
"""
import requests
import re
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL


class AgnesScenePromptGenerator:
    """使用 Agnes LLM 生成分镜提示词"""
    
    DESCRIPTION = "将分镜脚本转换为高质量的英文图像生成提示词，支持多种艺术风格"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scene_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入分镜脚本...",
                    "tooltip": "从场景切分或总导演节点输出的分镜文本"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key"
                }),
                "style": (["cinematic", "anime", "realistic", "watercolor", "oil_painting"], {
                    "default": "cinematic",
                    "tooltip": "图像风格：cinematic=电影感，anime=动漫，realistic=写实，watercolor=水彩，oil_painting=油画"
                }),
            },
            "optional": {
                "base_url": ("STRING", {
                    "default": BASE_URL,
                    "tooltip": "API 地址"
                }),
                "model": ("STRING", {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型"
                }),
                "characters_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "{\"characters\":[...]}",
                    "tooltip": "角色信息 JSON（从资产提取节点获取，可选）"
                }),
                "locations_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "{\"locations\":[...]}",
                    "tooltip": "场景信息 JSON（从资产提取节点获取，可选）"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("detailed_prompt",)
    RETURN_LABELS = ("英文提示词",)
    FUNCTION = "generate_prompt"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "detailed_prompt" in kwargs:
            extra["detailed_prompt"] = {
                "description": "转换为英文的详细图像生成提示词，包含主体描述、动作姿态、场景环境、光线设计、色彩影调、技术质量词"
            }
        return extra

    def generate_prompt(self, scene_text, api_key, style, base_url=BASE_URL, model=CHAT_MODEL, characters_json="", locations_json=""):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]",)
        print(f"\n{'='*50}")
        print(f"🖼️  Agnes 分镜提示词生成")
        print(f"{'='*50}")
        print(f"输入分镜: {scene_text[:200]}...")

        prompt = f"""你是一位世界顶级的AI图像生成提示词工程师，专精于将影视分镜脚本转换为高质量的AI生图提示词。

【任务】
将以下分镜脚本转换为一个极其详细的英文生图提示词。

【输入分镜脚本】
{scene_text}

【角色信息】（如有）
{characters_json}

【场景信息】（如有）
{locations_json}

【风格要求】
{style}

【提示词生成规则】

第一部分：主体描述
- 人物姓名、性别、年龄感
- 精确的服装描述：款式、材质、颜色、纹理、配饰
- 精确的面部表情：眉毛形态、眼神方向、嘴角状态
- 精确的情绪状态
- 人物在画面中的位置

第二部分：动作与姿态
- 身体姿态
- 手部动作
- 动态或静态描述

第三部分：场景与环境
- 最远景/背景
- 中景
- 近景/前景

第四部分：光线设计
- 主光源方向与类型
- 光质
- 光影效果

第五部分：色彩与影调
- 整体色调
- 饱和度与对比度

第六部分：技术质量词
- masterpiece, best quality, 8k, highly detailed, sharp focus
- cinematic lighting, film grain, 35mm
- rule of thirds composition, deep depth of field

【输出要求】
- 只输出一个完整的英文提示词段落
- 不要有任何额外解释
- 用逗号分隔各元素
- 提示词长度 150-300 词"""

        try:
            client = AgnesClient(api_key)
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.4,
                max_tokens=2000,
            )

            # 清理 markdown 标记
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

            print(f"[Agnes Prompt] 生成成功: {len(content)} 字符")
            return (content,)

        except Exception as e:
            print(f"[Agnes Prompt] 失败: {e}")
            return ("",)


NODE_CLASS_MAPPINGS = {"AgnesScenePromptGenerator": AgnesScenePromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScenePromptGenerator": "🎨 Agnes 分镜提示词生成"}
