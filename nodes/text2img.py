"""
Agnes Text-to-Image Node
========================
Generate images from text descriptions using Agnes AI image generation models.
Supports quality (1K/2K/4K) and aspect ratio selection.
"""

import torch

from ..api import (
    AgnesClient,
    get_api_key,
    IMAGE_MODEL,
    AVAILABLE_IMAGE_MODELS,
    pil_to_tensor,
    NEW_IMAGE_MODELS,
)
from ._output_docs import OutputDocsMixin

# Quality → short-side pixels
QUALITY_MAP = {
    "1K": 1024,
    "2K": 2048,
    "3K": 1536,
    "4K": 4096,
}

# Supported aspect ratios (width:height)
ASPECT_RATIOS = [
    "1:1",
    "2:3",
    "3:4",
    "4:5",
    "9:16",
    "9:21",
    "3:2",
    "4:3",
    "5:4",
    "16:9",
    "21:9",
]


def compute_size(quality: str, aspect_ratio: str) -> str:
    """
    Compute a WxH pixel size string from quality level and aspect ratio.

    quality: "1K" / "2K" / "4K" — determines the short-side pixel count.
    aspect_ratio: "W:H" — e.g. "16:9", "2:3".

    Returns: e.g. "1792x1024"
    """
    base = QUALITY_MAP.get(quality, 1024)
    w_ratio, h_ratio = map(int, aspect_ratio.split(":"))

    if w_ratio >= h_ratio:
        # Landscape or square: height = base, width scales up
        height = base
        width = base * w_ratio // h_ratio
    else:
        # Portrait: width = base, height scales up
        width = base
        height = base * h_ratio // w_ratio

    # Round to nearest 8 (common AI model alignment requirement)
    width = max(64, (width // 8) * 8)
    height = max(64, (height // 8) * 8)

    return f"{width}x{height}"


class AgnesNovelTextToImage(OutputDocsMixin):
    """Agnes AI Text-to-Image node for ComfyUI."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("images", "resolution",)
    RETURN_LABELS = ('输出图像', '分辨率')
    OUTPUT_DOCS = {
        "images": "生成的图像张量（1=单图，n>1 时批量），可连接 SaveImage 或视频节点作为参考图",
        "resolution": "本次输出的实际分辨率（WxH）；新接口 2.5-flash 按档位+比例出图，分辨率以实际返回为准",
    }
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "A beautiful sunset over mountains...",
                    "tooltip": "Text description of the image to generate",
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
                "model": (AVAILABLE_IMAGE_MODELS, {
                    "default": IMAGE_MODEL,
                    "tooltip": "Image generation model",
                }),
                "quality": (["1K", "2K", "3K", "4K"], {
                    "default": "1K",
                    "tooltip": "Image quality / short-side resolution. 1K=1024px, 2K=2048px, 3K/4K for new image-2.5 model",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "1:1",
                    "tooltip": "Output aspect ratio (width:height). E.g. 16:9 for widescreen, 2:3 for portrait",
                }),
                "n": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 4,
                    "step": 1,
                    "tooltip": "单次请求生成张数：旧接口支持 1-4；新接口 agnes-image-2.5-flash 的 API 不支持 n 参数，固定出 1 张",
                }),
            },
        }

    def generate(
        self,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = IMAGE_MODEL,
        quality: str = "1K",
        aspect_ratio: str = "1:1",
        n: int = 1,
    ):
        size = compute_size(quality, aspect_ratio)
        w, h = map(int, size.split("x"))

        if not prompt.strip():
            black = torch.zeros(1, h, w, 3)
            return (black, "[Error: Prompt is empty. Please provide an image description.]")

        # Runtime fallback: try config file if widget value is empty
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            black = torch.zeros(1, h, w, 3)
            return (black, "[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                # 新接口：size 传档位（1K/2K/3K/4K）+ ratio
                pil_images = client.generate_image(
                    prompt=prompt.strip(),
                    mode="text2img",
                    size=quality.upper(),
                    ratio=aspect_ratio,
                    n=n,
                    model=model,
                )
            else:
                # 旧接口：size 传 WxH 像素
                pil_images = client.generate_image(
                    prompt=prompt.strip(),
                    mode="text2img",
                    size=size,
                    n=n,
                    model=model,
                )

            if not pil_images:
                black = torch.zeros(1, h, w, 3)
                return (black, "[Error: No images were generated. Check your prompt and try again.]")

            # Convert to ComfyUI tensor batch
            tensors = [pil_to_tensor(img) for img in pil_images]
            batch = tensors[0] if len(tensors) == 1 else torch.cat(tensors, dim=0)

            return (batch, size)
        except Exception as e:
            black = torch.zeros(1, h, w, 3)
            return (black, f"[Error] {str(e)}")

NODE_CLASS_MAPPINGS = {"AgnesNovelTextToImage": AgnesNovelTextToImage}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelTextToImage": "Agnes 文生图"}
