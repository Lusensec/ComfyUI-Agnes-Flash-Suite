"""
Agnes Image Reverse Prompt Node
===============================
Analyzes an input image and generates a detailed AI image generation prompt
that describes the image. Uses Agnes-2.0-Flash vision capability.
"""

from typing import Tuple

from ..api import AgnesClient, get_api_key, CHAT_MODEL, AVAILABLE_CHAT_MODELS, tensor_to_pil
from ._output_docs import OutputDocsMixin


class AgnesNovelImageReverse(OutputDocsMixin):
    """Agnes AI Image Reverse Prompt node - generates prompts from images."""

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
                    "tooltip": "Input image to analyze for prompt generation",
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
                    "tooltip": "Your Agnes AI API key",
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "Vision-capable model for image analysis",
                }),
            },
        }

    def reverse(self, image=None, model: str = CHAT_MODEL, base_url: str = "", api_key: str = "") -> Tuple[str, str]:
        # Runtime fallback: try config file if widget value is empty
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[Error: API key is required]"
            return (err, err)

        try:
            # Convert ComfyUI tensor to PIL
            pil_img = tensor_to_pil(image)

            client = AgnesClient(api_key, base_url=base_url.strip() or None)

            # Generate detailed prompt
            detailed = client.reverse_prompt(pil_img, model=model, detail="detailed")

            # Generate brief prompt
            brief = client.reverse_prompt(pil_img, model=model, detail="brief")

            return (detailed, brief)
        except Exception as e:
            err = f"[Error] {str(e)}"
            return (err, err)

NODE_CLASS_MAPPINGS = {"AgnesNovelImageReverse": AgnesNovelImageReverse}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelImageReverse": "🔍 Agnes 图像反推提示词"}
