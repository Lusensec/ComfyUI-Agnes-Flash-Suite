"""
Agnes 图像反推提示词节点
==========================
分析输入图像，生成可复现该图的详细 AI 图像生成提示词。
使用 Agnes 文本模型（默认 agnes-2.5-flash）的视觉理解能力。
"""

from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
    normalize_reasoning_effort,
    tensor_to_pil,
)
from ._output_docs import OutputDocsMixin


class AgnesNovelImageReverse(OutputDocsMixin):
    """Agnes AI 图像反推提示词节点：分析图像生成描述该图的提示词。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("prompt", "brief_prompt",)
    RETURN_LABELS = ('详细提示词', '简洁提示词')
    OUTPUT_DOCS = {
        "prompt": "详细版提示词：完整描述画面主体/场景/风格/光照/构图，可直接用于文生图节点",
        "brief_prompt": "简洁版提示词：压缩后的关键词形式，适合快速生图或作为基础提示词再加工",
    }
    FUNCTION = "reverse"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "待分析的图片（用于反推生成提示词）",
                }),
                "base_url": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key（留空则跟随全局配置：环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）",
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "视觉模型（用于图像分析）：默认 agnes-2.5-flash，可选 3.0/2.5/2.0-flash",
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型视觉识别）：auto=跟随模型默认 / none / low / medium / high / max；2.0 旧模型不生效",
                }),
            },
        }

    def reverse(self, image=None, model: str = CHAT_MODEL, base_url: str = "", api_key: str = "", reasoning_effort: str = "auto") -> Tuple[str, str]:
        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置"
            return (err, err)

        try:
            # ComfyUI 图像张量转 PIL
            pil_img = tensor_to_pil(image)

            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            effort = normalize_reasoning_effort(reasoning_effort)

            # 生成详细版提示词（detailed）
            detailed = client.reverse_prompt(pil_img, model=model, detail="detailed", reasoning_effort=effort)

            # 生成简洁版提示词（brief）
            brief = client.reverse_prompt(pil_img, model=model, detail="brief", reasoning_effort=effort)

            return (detailed.strip(), brief.strip())
        except Exception as e:
            err = f"[Error] {str(e)}"
            return (err, err)

NODE_CLASS_MAPPINGS = {"AgnesNovelImageReverse": AgnesNovelImageReverse}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelImageReverse": "🔍 Agnes 图像反推提示词"}
