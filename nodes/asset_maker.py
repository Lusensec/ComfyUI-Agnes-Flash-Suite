# -*- coding: utf-8 -*-
"""
Agnes 定妆图生成器（带"已存在跳过"）
=====================================
两段式漫剧管线「工作流 A（前置定妆）」的定妆区节点：

每个资产一个该节点，逻辑：
  1. 检查 output/agnes_assets/ 下是否已有该资产的定妆图
  2. 已存在 → 直接读取本地图返回（♻️ 复用，不调用 API、不重新生成）
  3. 不存在 → 调用 Agnes 文生图 API 生成 → 保存到本地（🆕 生成并持久化）

从而实现跨章节一致性：
  第 1 章生成全部定妆图 → 后续章节老资产自动复用、新资产才生成。
"""
import os
import re
import time

import torch
import folder_paths

from ..api import (
    AgnesClient,
    get_api_key,
    pil_to_tensor,
    IMAGE_MODEL,
    AVAILABLE_IMAGE_MODELS,
    NEW_IMAGE_MODELS,
)

QUALITY_MAP = {"1K": 1024, "2K": 2048, "3K": 1536, "4K": 4096}
ASPECT_RATIOS = ["1:1", "2:3", "3:4", "4:5", "9:16", "9:21",
                 "3:2", "4:3", "5:4", "16:9", "21:9"]
IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def compute_size(quality, aspect_ratio):
    """从画质+比例计算 WxH 尺寸（与 text2img 节点一致）"""
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


class AgnesAssetMaker:
    """定妆图生成器：已存在则复用，不存在则生成并保存"""

    DESCRIPTION = "定妆图生成器：检查本地已有定妆图→复用；没有→生成并保存（跨章节一致性核心）"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prefix": ("STRING", {
                    "default": "",
                    "placeholder": "agnes_assets/characters_白奕",
                    "tooltip": "资产保存前缀（含类型+名称），由 AgnesAssetJsonSplitter 的 prefix_N 输出提供"
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Character concept sheet, ...",
                    "tooltip": "定妆图英文提示词（由 AgnesAssetJsonSplitter 的 prompt_N 输出提供）"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key"
                }),
                "quality": (["1K", "2K", "3K", "4K"], {
                    "default": "2K",
                    "tooltip": "画质：1K/2K/3K/4K（新图像模型按档位计费，2K 性价比最高）"
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "16:9",
                    "tooltip": "画面比例"
                }),
                "model": (AVAILABLE_IMAGE_MODELS, {
                    "default": IMAGE_MODEL,
                    "tooltip": "图像生成模型"
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING",)
    RETURN_NAMES = ("images", "status",)
    RETURN_LABELS = ("定妆图", "状态")
    FUNCTION = "make"
    CATEGORY = "Agnes Novel"

    def make(self, prefix, prompt, api_key, quality="2K",
             aspect_ratio="16:9", model=IMAGE_MODEL):
        prefix = (prefix or "").strip()
        prompt = (prompt or "").strip()

        # 空槽位（无资产）：返回黑色占位图，不调用 API
        if not prefix or not prompt:
            black = torch.zeros(1, 64, 64, 3)
            return (black, "⏭️ 空槽位（无资产），跳过")

        # 解析前缀: "agnes_assets/characters_白奕" -> (子目录, 文件基名)
        parts = prefix.replace("\\", "/").split("/")
        base_name = parts[-1] if parts else prefix
        rel_dir = "/".join(parts[:-1]) if len(parts) > 1 else ""
        output_dir = folder_paths.get_output_directory()
        asset_dir = os.path.join(output_dir, rel_dir) if rel_dir else output_dir
        os.makedirs(asset_dir, exist_ok=True)

        # ---------- 1. 已存在检测：直接复用 ----------
        existing = self._find_existing(asset_dir, base_name)
        if existing:
            try:
                from PIL import Image
                img = Image.open(existing).convert("RGB")
                tensor = pil_to_tensor(img)
                return (tensor, f"♻️ 复用已有定妆图: {existing}")
            except Exception:
                pass  # 文件损坏则重新生成

        # ---------- 2. 生成 + 保存 ----------
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            black = torch.zeros(1, 64, 64, 3)
            return (black, "[Error] API key 缺失，无法生成定妆图")

        try:
            client = AgnesClient(api_key)
            if model in NEW_IMAGE_MODELS:
                # 新接口：size 传档位（1K/2K/3K/4K）+ ratio
                size_arg, ratio_arg = quality.upper(), aspect_ratio
            else:
                # 旧接口：size 传 WxH 像素
                size_arg, ratio_arg = compute_size(quality, aspect_ratio), None
            pil_images = client.generate_image(
                prompt=prompt,
                mode="text2img",
                size=size_arg,
                n=1,
                model=model,
                ratio=ratio_arg,
            )
            if not pil_images:
                black = torch.zeros(1, 64, 64, 3)
                return (black, "[Error] 图像生成失败（无返回）")

            img = pil_images[0]
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 保存: characters_白奕_20260818_230000_00001_.png
            ts = time.strftime("%Y%m%d_%H%M%S")
            fname = f"{base_name}_{ts}_00001_.png"
            fpath = os.path.join(asset_dir, fname)
            img.save(fpath, "PNG")

            tensor = pil_to_tensor(img)
            return (tensor, f"🆕 已生成并保存: {fpath}")
        except Exception as e:
            black = torch.zeros(1, 64, 64, 3)
            return (black, f"[Error] {e}")

    # ==========================================================
    # 内部工具
    # ==========================================================

    def _find_existing(self, asset_dir, base_name):
        """查找是否已有以 base_name 开头的定妆图，返回第一个匹配的完整路径"""
        if not os.path.isdir(asset_dir):
            return None
        for fname in os.listdir(asset_dir):
            if not fname.lower().endswith(IMG_EXTS):
                continue
            # 匹配 "characters_白奕_xxx.png"（base_name 后跟 _ 或直接扩展名）
            if fname.startswith(base_name + "_") or fname.startswith(base_name + "."):
                return os.path.join(asset_dir, fname)
        return None


NODE_CLASS_MAPPINGS = {"AgnesAssetMaker": AgnesAssetMaker}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetMaker": "🖼️ Agnes 定妆图生成器"}
