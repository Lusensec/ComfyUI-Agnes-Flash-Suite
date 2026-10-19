"""
Agnes 图生图（Image-to-Image）节点
===================================
使用 Agnes AI 图像生成模型编辑或变换图像。
支持多图输入 - 可传入多张参考图共同指导生成过程（最多 6 张）。
支持画质档位（1K/2K/3K/4K）与宽高比选择。
"""

import torch

from ..api import (
    AgnesClient,
    get_api_key,
    IMAGE_MODEL,
    AVAILABLE_IMAGE_MODELS,
    tensor_to_pil,
    pil_to_tensor,
    NEW_IMAGE_MODELS,
)
from ._output_docs import OutputDocsMixin

# 画质档位 → 短边像素
QUALITY_MAP = {
    "1K": 1024,
    "2K": 2048,
    "3K": 1536,
    "4K": 4096,
}

# 支持的宽高比（宽:高）
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
    根据画质档位与宽高比计算 WxH 像素尺寸字符串。

    quality: "1K" / "2K" / "4K" — 决定短边像素数。
    aspect_ratio: "W:H" — 例如 "16:9"、"2:3"。

    返回：例如 "1792x1024"
    """
    base = QUALITY_MAP.get(quality, 1024)
    w_ratio, h_ratio = map(int, aspect_ratio.split(":"))

    if w_ratio >= h_ratio:
        height = base
        width = base * w_ratio // h_ratio
    else:
        width = base
        height = base * h_ratio // w_ratio

    width = max(64, (width // 8) * 8)
    height = max(64, (height // 8) * 8)

    return f"{width}x{height}"


class AgnesNovelImageToImage(OutputDocsMixin):
    """Agnes AI 图生图（图像编辑）节点：以参考图为底，按提示词编辑/变换，支持多图输入。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("images", "resolution",)
    RETURN_LABELS = ('输出图像', '分辨率')
    OUTPUT_DOCS = {
        "images": "编辑/生成后的图像张量（n>1 时为批量），可连接 SaveImage 或视频节点",
        "resolution": "本次输出的实际分辨率（WxH）；新接口 2.5-flash 按档位+比例出图",
    }
    FUNCTION = "edit"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "主参考图（必接）：图生图以此图为底做编辑/变换；可再接最多 5 张额外参考图（合计最多 6 张）",
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入变换描述（建议英文），例如：Make it look like a watercolor painting...",
                    "tooltip": "描述想要的变换效果（建议英文提示词）",
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
                "model": (AVAILABLE_IMAGE_MODELS, {
                    "default": IMAGE_MODEL,
                    "tooltip": "图像生成模型（默认 agnes-image-2.5-flash；旧接口 2.1/2.0 按 WxH 像素出图）",
                }),
                "quality": (["1K", "2K", "3K", "4K"], {
                    "default": "1K",
                    "tooltip": "画质档位（短边分辨率）：新接口 2.5-flash 按 1K/2K/3K/4K 档位出图（3K/4K 面向新 2.5 模型）；旧接口 2.1/2.0 换算为 WxH 像素",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "1:1",
                    "tooltip": "输出宽高比（宽:高）：与画质档位组合出图，如 16:9 宽屏、2:3 竖版；新接口不支持的比例自动就近映射",
                }),
                "strength": ("FLOAT", {
                    "default": 0.75,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "变化强度。注意：Agnes API 没有 strength 参数，本节点将其转成提示词指令（越低越贴近原图，1.0=完全按提示词改变）",
                }),
                "n": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 4,
                    "step": 1,
                    "tooltip": "单次请求生成张数：旧接口支持 1-4；新接口 agnes-image-2.5-flash 的 API 不支持 n 参数，固定出 1 张",
                }),
            },
            "optional": {
                "reference_image_2": ("IMAGE", {
                    "tooltip": "额外参考图 2（多图输入，合计最多 6 张）",
                }),
                "reference_image_3": ("IMAGE", {
                    "tooltip": "额外参考图 3（多图输入，合计最多 6 张）",
                }),
                "reference_image_4": ("IMAGE", {
                    "tooltip": "额外参考图 4（多图输入，合计最多 6 张）",
                }),
                "reference_image_5": ("IMAGE", {
                    "tooltip": "额外参考图 5（多图输入，合计最多 6 张）",
                }),
                "reference_image_6": ("IMAGE", {
                    "tooltip": "额外参考图 6（多图输入，合计最多 6 张）",
                }),
            },
        }

    def edit(
        self,
        image=None,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = IMAGE_MODEL,
        quality: str = "1K",
        aspect_ratio: str = "1:1",
        strength: float = 0.75,
        n: int = 1,
        reference_image_2=None,
        reference_image_3=None,
        reference_image_4=None,
        reference_image_5=None,
        reference_image_6=None,
    ):
        size = compute_size(quality, aspect_ratio)
        w, h = map(int, size.split("x"))

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            black = torch.zeros(1, h, w, 3)
            return (black, "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）")
        if not prompt.strip():
            black = torch.zeros(1, h, w, 3)
            return (black, "[错误] 提示词为空：请描述想要的变换效果")

        # 收集全部参考图（主图 + 额外参考图）
        ref_imgs = [tensor_to_pil(image)]

        for ref in [reference_image_2, reference_image_3, reference_image_4,
                    reference_image_5, reference_image_6]:
            if ref is not None:
                ref_imgs.append(tensor_to_pil(ref))

        # strength < 1.0 时转成提示词指令附在提示词尾部（保持英文，与模型提示词语言一致）
        full_prompt = prompt.strip()
        if strength < 1.0:
            full_prompt = (
                f"{full_prompt}\n"
                f"[Guidance: transformation strength = {strength:.0%}. "
                f"Lower strength means stay closer to the original.]"
            )

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                # 新接口：size 传档位 + ratio，参考图走 extra_body.image[]
                pil_images = client.generate_image(
                    prompt=full_prompt,
                    mode="img2img",
                    reference_images=ref_imgs,
                    size=quality.upper(),
                    ratio=aspect_ratio,
                    n=n,
                    model=model,
                )
            else:
                # 旧接口：size 传 WxH 像素
                pil_images = client.generate_image(
                    prompt=full_prompt,
                    mode="img2img",
                    reference_images=ref_imgs,
                    size=size,
                    n=n,
                    model=model,
                )

            if not pil_images:
                black = torch.zeros(1, h, w, 3)
                return (black, "[错误] 未生成任何图片：请检查输入后重试")

            # 转换为 ComfyUI 图像张量（n>1 时批量）
            tensors = [pil_to_tensor(img) for img in pil_images]
            batch = tensors[0] if len(tensors) == 1 else torch.cat(tensors, dim=0)

            return (batch, size)
        except Exception as e:
            black = torch.zeros(1, h, w, 3)
            return (black, f"[Error] {str(e)}")

NODE_CLASS_MAPPINGS = {"AgnesNovelImageToImage": AgnesNovelImageToImage}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelImageToImage": "🖼️ Agnes 图生图"}
