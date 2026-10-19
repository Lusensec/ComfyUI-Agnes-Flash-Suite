"""
Agnes 图像生成节点
使用 Agnes Image API（默认 agnes-image-2.5-flash，可选旧 2.1/2.0）
支持 n=1-4 批量出图（旧接口生效；新 2.5-flash 固定 1 张），
已合并原 Agnes 文生图（AgnesNovelTextToImage）的多张生成功能，该节点已删除。
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
    AVAILABLE_IMAGE_MODELS,
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
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入英文图像描述...",
                    "tooltip": "从分镜提示词生成节点输出的英文提示词"
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
                "model": (AVAILABLE_IMAGE_MODELS, {
                    "default": IMAGE_MODEL,
                    "tooltip": "图像生成模型（当前默认 agnes-image-2.5-flash；选旧模型时 width/height 按像素生效）"
                }),
                "width": ("INT", {
                    "default": 1920,
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "tooltip": "图像宽度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效；新接口 agnes-image-2.5-flash 用 quality 档位 + aspect_ratio 出图"
                }),
                "height": ("INT", {
                    "default": 1080,
                    "min": 512,
                    "max": 2048,
                    "step": 64,
                    "tooltip": "图像高度（像素）：仅旧接口 2.1/2.0 按 WxH 像素生效；新接口 agnes-image-2.5-flash 用 quality 档位 + aspect_ratio 出图"
                }),
                "quality": (["1K", "2K", "3K", "4K"], {
                    "default": "1K",
                    "tooltip": "画质档位：新接口 agnes-image-2.5-flash 按 1K/2K/3K/4K 档位出图；旧接口 1K/2K"
                }),
                "aspect_ratio": (["1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9"], {
                    "default": "16:9",
                    "tooltip": "宽高比（与视频节点一致）：新接口 agnes-image-2.5-flash 与 quality 档位组合出图，如 16:9 + 2K = 2624×1472；旧接口 2.1/2.0 按 width/height 像素出图，此项不生效"
                }),
                "n": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 4,
                    "step": 1,
                    "tooltip": "单次请求生成张数（1-4）：当前 Agnes 服务端对所有图像模型限单张（n>1 返回 400，节点自动降级为 1 张并打印提示）；API 解锁多张后 n 直接生效。n>1 成功时输出批量张量（同主体多张变体；多资产请多节点实例各出 1 张）",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "url", "resolution",)
    RETURN_LABELS = ("图像张量", "图片 URL", "分辨率")
    OUTPUT_TOOLTIPS = (
        "生成的图像张量（n=1 单张；n>1 时批量 (N,H,W,3)；连接 SaveImage 存档，或图生视频/三视图节点作为参考图）",
        "图片 URL / 本地保存路径（可下载或记录引用）",
        "本次输出的实际分辨率（WxH）",
    )
    FUNCTION = "generate"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "image" in kwargs:
            extra["image"] = {"description": "生成的图像张量（n>1 时批量），可连接 SaveImage 存档或视频生成节点"}
        if "url" in kwargs:
            extra["url"] = {"description": "图片的 URL 地址"}
        if "resolution" in kwargs:
            extra["resolution"] = {"description": "本次输出的实际分辨率（WxH）"}
        return extra

    def generate(self, prompt="", base_url="", api_key="", width=1920, height=1080, quality="1K", model=IMAGE_MODEL, aspect_ratio="16:9", n=1):
        n = max(1, min(4, int(n or 1)))
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            import torch as _torch
            err_msg = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            black = _torch.zeros(1, height, width, 3)
            return (black, err_msg, "")
        print(f"\n[Agnes Image] 开始生成...")
        print(f"Prompt: {prompt[:80]}...")
        print(f"Model: {model}, Quality: {quality}, 尺寸: {width}x{height}, 比例: {aspect_ratio}, 张数: {n}")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                # 新接口：档位（1K/2K/3K/4K）+ 显式宽高比 ratio；客户端已下载并转 PIL
                # 注意：新接口 API 不支持 n 参数，实际固定出 1 张
                size_arg, ratio_arg = quality.upper(), (aspect_ratio or _nearest_ratio(width, height))
            else:
                # 旧接口：WxH 像素（ratio 不参与）
                size_arg, ratio_arg = f"{width}x{height}", None
            def _call(nn):
                return client.generate_image(
                    prompt=prompt,
                    model=model,
                    size=size_arg,
                    ratio=ratio_arg,
                    n=nn,
                )

            try:
                pil_images = _call(n)
            except Exception as e:
                # 服务端限制单张出图（n 必须为 1）时自动降级
                if n > 1 and ("n 必须为 1" in str(e) or "n must be 1" in str(e)):
                    print(f"[Agnes Image] {model} 暂不支持 n={n} 多张（服务端限单张，400），自动降级 n=1")
                    n = 1
                    pil_images = _call(1)
                else:
                    raise

            if pil_images:
                tensors = []
                for pil_img in pil_images:
                    if pil_img.mode != "RGB":
                        pil_img = pil_img.convert("RGB")
                    img_np = np.array(pil_img).astype(np.float32) / 255.0
                    tensors.append(torch.from_numpy(img_np).unsqueeze(0))
                batch = tensors[0] if len(tensors) == 1 else torch.cat(tensors, dim=0)
                res = f"{pil_images[0].size[0]}x{pil_images[0].size[1]}"
                print(f"[Agnes Image] 生成成功: {res} x {len(tensors)} 张")
                return (batch, "", res)
            else:
                raise Exception("未获取到图片")

        except Exception as e:
            print(f"[Agnes Image] 失败: {e}")
            # 返回黑色图片作为占位
            black = torch.zeros(1, height, width, 3)
            return (black, "", "")


NODE_CLASS_MAPPINGS = {"AgnesImageGen": AgnesImageGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesImageGen": "🎨 Agnes 图像生成"}
