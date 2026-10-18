"""
Agnes 图像生成节点
使用 Agnes Image API (agnes-image-2.1-flash)
"""
import requests
import torch
import numpy as np
from PIL import Image
import io
import folder_paths
from ..api import (
    AgnesClient,
    get_api_key,
    BASE_URL,
    IMAGE_MODEL,
    NEW_IMAGE_MODELS,
)

# 宽高比就近匹配表（节点 width/height → 新图像接口支持的 8 种 ratio）
_RATIOS_W_H = [
    ("1:1", 1.0), ("3:4", 3 / 4), ("4:3", 4 / 3), ("16:9", 16 / 9),
    ("9:16", 9 / 16), ("2:3", 2 / 3), ("3:2", 3 / 2), ("21:9", 21 / 9),
]


def _nearest_ratio(width, height):
    """把 width/height 映射到新图像接口支持的比例（误差最小者）"""
    r = width / height if height else 1.0
    return min(_RATIOS_W_H, key=lambda t: abs(t[1] - r))[0]


class AgnesImageGen:
    """使用 Agnes AI 生成图像"""
    
    DESCRIPTION = "根据英文提示词生成高质量图像，支持多种尺寸和画质选项"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整"
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入英文图像描述...",
                    "tooltip": "从分镜提示词生成节点输出的英文提示词"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key"
                }),
                "width": ("INT", {
                    "default": 1920,
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "tooltip": "图像宽度，推荐 1920（16:9）或 1080（9:16）"
                }),
                "height": ("INT", {
                    "default": 1080,
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "tooltip": "图像高度，推荐 1080（16:9）或 1920（9:16）"
                }),
                "quality": (["1K", "2K"], {
                    "default": "1K",
                    "tooltip": "画质等级：1K=性价比最高，2K=更高分辨率（消耗更多配额）"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("image", "url",)
    RETURN_LABELS = ("图像张量", "图片 URL")
    FUNCTION = "generate"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "image" in kwargs:
            extra["image"] = {"description": "生成的图像张量，可连接视频生成节点"}
        if "url" in kwargs:
            extra["url"] = {"description": "图片的 URL 地址"}
        return extra

    def generate(self, base_url="", prompt="", api_key="", width=1920, height=1080, quality="1K"):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            import torch as _torch
            err_msg = "[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]"
            black = _torch.zeros(1, height, width, 3)
            return (black, err_msg)
        print(f"\n[Agnes Image] 开始生成...")
        print(f"Prompt: {prompt[:80]}...")
        print(f"Size: {width}x{height}, Quality: {quality}, Model: {IMAGE_MODEL}")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if IMAGE_MODEL in NEW_IMAGE_MODELS:
                # 新接口：档位（1K/2K）+ 比例，客户端已下载并转 PIL
                size_arg, ratio_arg = quality.upper(), _nearest_ratio(width, height)
            else:
                # 旧接口：WxH 像素
                size_arg, ratio_arg = f"{width}x{height}", None
            pil_images = client.generate_image(
                prompt=prompt,
                model=IMAGE_MODEL,
                size=size_arg,
                ratio=ratio_arg,
                n=1,
            )

            if pil_images:
                pil_img = pil_images[0]
                if pil_img.mode != "RGB":
                    pil_img = pil_img.convert("RGB")

                # 转换为 ComfyUI 格式
                img_np = np.array(pil_img).astype(np.float32) / 255.0
                img_tensor = torch.from_numpy(img_np).unsqueeze(0)

                print(f"[Agnes Image] 生成成功: {pil_img.size}")
                return (img_tensor, "")
            else:
                raise Exception("未获取到图片")

        except Exception as e:
            print(f"[Agnes Image] 失败: {e}")
            # 返回黑色图片作为占位
            black = torch.zeros(1, height, width, 3)
            return (black, "")


NODE_CLASS_MAPPINGS = {"AgnesImageGen": AgnesImageGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesImageGen": "🎨 Agnes 图像生成"}
