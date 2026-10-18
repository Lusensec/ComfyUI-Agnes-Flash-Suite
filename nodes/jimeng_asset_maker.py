# -*- coding: utf-8 -*-
"""
JimengAssetMaker - 使用即梦API生成定妆图
=====================================
替代原AgnesAssetMaker，使用Jimeng高质量图像生成模型。

逻辑：
  1. 检查 output/agnes_assets/ 下是否已有该资产的定妆图
  2. 已存在 → 直接读取本地图返回（♻️ 复用，不调用 API）
  3. 不存在 → 调用 Jimeng 文生图 API 生成 → 保存到本地

支持类型：
  - 角色定妆图：characters_XXX
  - 场景定妆图：locations_XXX
  - 道具定妆图：props_XXX
  - 服装定妆图：costumes_XXX
  - 天气定妆图：weather_XXX
"""
import os
import time
import torch
import folder_paths

# 尝试从jimeng节点导入客户端
try:
    import sys
    # comfyui-jimeng 是 ComfyUI custom_nodes 下的兄弟插件：
    #   custom_nodes/Comfyui-Agnes-Flash-Suite/nodes/jimeng_asset_maker.py
    # 需向上 3 级 dirname 到 custom_nodes，再进入 comfyui-jimeng/nodes
    jimeng_path = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        ),
        "comfyui-jimeng", "nodes"
    )
    if jimeng_path not in sys.path:
        sys.path.insert(0, jimeng_path)
    from jimeng_client import (
        JimengClient,
        DEFAULT_BASE_URL,
        IMAGE_MODELS,
        DEFAULT_IMAGE_MODEL,
        RATIOS,
        IMAGE_RESOLUTIONS,
    )
except ImportError:
    # 降级：使用占位符
    JimengClient = None
    DEFAULT_BASE_URL = "http://127.0.0.1:8001"
    IMAGE_MODELS = ["jimeng-image-5.0-pro", "jimeng-image-5.0-lite"]
    DEFAULT_IMAGE_MODEL = "jimeng-image-5.0-lite"
    RATIOS = ["1:1", "16:9", "9:16"]
    IMAGE_RESOLUTIONS = ["1k", "2k", "4k"]


# 定妆图目录
DEFAULT_ASSET_DIR = "agnes_assets"
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# 资产类型前缀映射
_ASSET_TYPE_PREFIXES = [
    "characters_", "locations_", "props_", "costumes_", "weather_"
]


def pil_to_tensor(img):
    """PIL.Image(RGB) -> torch.Tensor (1,H,W,3)"""
    import numpy as np
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def tensor_to_pil(tensor):
    """torch.Tensor (B,H,W,3) -> PIL.Image（取第0帧）"""
    from PIL import Image
    import numpy as np
    t = tensor[0].cpu()
    arr = (t.clamp(0, 1) * 255).to(torch.uint8).numpy()
    return Image.fromarray(arr, "RGB")


def compute_size(ratio: str, resolution: str) -> str:
    """根据ratio和resolution计算尺寸"""
    ratio_map = {
        "1:1": (1, 1),
        "16:9": (16, 9),
        "9:16": (9, 16),
        "4:3": (4, 3),
        "3:4": (3, 4),
        "2:3": (2, 3),
        "3:2": (3, 2),
        "21:9": (21, 9),
    }
    res_map = {"1k": 1024, "1.5k": 1536, "2k": 2048, "4k": 4096}

    base = res_map.get(resolution, 2048)
    w_ratio, h_ratio = ratio_map.get(ratio, (16, 9))

    if w_ratio >= h_ratio:
        height = base
        width = base * w_ratio // h_ratio
    else:
        width = base
        height = base * h_ratio // w_ratio

    # Round to nearest 64
    width = max(64, (width // 64) * 64)
    height = max(64, (height // 64) * 64)

    return f"{width}x{height}"


class JimengAssetMaker:
    """使用Jimeng生成定妆图：已存在则复用，不存在则生成"""

    DESCRIPTION = "Jimeng定妆图生成器：检查本地已有定妆图→复用；没有→调用即梦API生成"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prefix": ("STRING", {
                    "default": "",
                    "placeholder": "characters_白奕",
                    "tooltip": "资产前缀，如 characters_白奕、locations_客栈"
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Character concept sheet, full body, three views...",
                    "tooltip": "定妆图英文提示词"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "即梦sessionid",
                    "tooltip": "jimeng-free-api的Authorization Bearer值"
                }),
                "base_url": ("STRING", {
                    "default": DEFAULT_BASE_URL,
                    "tooltip": "jimeng-free-api服务地址（默认127.0.0.1:8001）"
                }),
                "model": (IMAGE_MODELS, {
                    "default": DEFAULT_IMAGE_MODEL,
                    "tooltip": "即梦图像模型"
                }),
                "ratio": (RATIOS, {
                    "default": "16:9",
                    "tooltip": "画面比例"
                }),
                "resolution": (IMAGE_RESOLUTIONS, {
                    "default": "2k",
                    "tooltip": "分辨率：1k/1.5k/2k/4k"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("images", "status",)
    RETURN_LABELS = ("定妆图", "状态")
    FUNCTION = "make"
    CATEGORY = "Agnes Novel"

    def make(self, prefix, prompt, api_key, base_url, model, ratio, resolution):
        prefix = (prefix or "").strip()
        prompt = (prompt or "").strip()
        base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        api_key = (api_key or "").strip()

        # 空槽位：返回黑色占位图
        if not prefix or not prompt:
            black = torch.zeros(1, 64, 64, 3)
            return (black, "⏭️ 空槽位，跳过")

        # 解析资产类型和名称
        asset_type = None
        asset_name = prefix
        for p in _ASSET_TYPE_PREFIXES:
            if prefix.startswith(p):
                asset_type = p[:-1]  # 去掉末尾下划线
                asset_name = prefix[len(p):]
                break

        # 获取输出目录
        output_dir = folder_paths.get_output_directory()
        asset_dir = os.path.join(output_dir, DEFAULT_ASSET_DIR)
        os.makedirs(asset_dir, exist_ok=True)

        # ========== 1. 检查是否已有定妆图 ==========
        existing = self._find_existing(asset_dir, asset_name, asset_type)
        if existing:
            try:
                from PIL import Image
                img = Image.open(existing).convert("RGB")
                tensor = pil_to_tensor(img)
                return (tensor, f"♻️ 复用已有: {os.path.basename(existing)}")
            except Exception as e:
                print(f"[JimengAssetMaker] 读取失败，重新生成: {e}")

        # ========== 2. 调用Jimeng生成 ==========
        if not api_key:
            black = torch.zeros(1, 64, 64, 3)
            return (black, "[Error] API key 不能为空")

        try:
            if JimengClient is None:
                raise RuntimeError("JimengClient未导入，请确认comfyui-jimeng插件已安装")

            client = JimengClient(base_url, api_key)
            size = compute_size(ratio, resolution)
            w, h = map(int, size.split("x"))

            print(f"[JimengAssetMaker] 生成定妆图: {prefix}")
            print(f"  Prompt: {prompt[:100]}...")
            print(f"  Size: {size}, Model: {model}")

            imgs = client.generate_image(
                prompt=prompt.strip(),
                model=model,
                ratio=ratio,
                resolution=resolution,
                n=1,
            )

            if not imgs:
                black = torch.zeros(1, 64, 64, 3)
                return (black, "[Error] 即梦未返回图片")

            img = imgs[0]
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 保存
            ts = time.strftime("%Y%m%d_%H%M%S")
            if asset_type:
                fname = f"{asset_type}_{asset_name}_{ts}_00001_.png"
            else:
                fname = f"{asset_name}_{ts}_00001_.png"
            fpath = os.path.join(asset_dir, fname)
            img.save(fpath, "PNG")

            tensor = pil_to_tensor(img)
            return (tensor, f"🆕 已生成: {fname}")

        except Exception as e:
            print(f"[JimengAssetMaker] 失败: {e}")
            black = torch.zeros(1, 64, 64, 3)
            return (black, f"[Error] {e}")

    def _find_existing(self, asset_dir, asset_name, asset_type=None):
        """查找是否已有定妆图"""
        if not os.path.isdir(asset_dir):
            return None
        for fname in os.listdir(asset_dir):
            if not fname.lower().endswith(IMG_EXTS):
                continue
            # 匹配模式：assets_type_name_xxx.png
            if asset_type:
                pattern = f"{asset_type}_{asset_name}_"
            else:
                pattern = f"{asset_name}_"
            if fname.startswith(pattern):
                return os.path.join(asset_dir, fname)
        return None


NODE_CLASS_MAPPINGS = {"JimengAssetMaker": JimengAssetMaker}
NODE_DISPLAY_NAME_MAPPINGS = {"JimengAssetMaker": "🖼️ Jimeng 定妆图生成器"}
