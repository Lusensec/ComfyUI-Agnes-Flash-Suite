# -*- coding: utf-8 -*-
"""
Agnes 角色三视图设定图节点
===========================
生成角色三视图设定表（turnaround sheet）：
同一角色的 正面 / 侧面 / 背面 三个视图从左到右并排排列，
全身完整展示、正交视图、比例与服装发型细节一致。

可选连接角色定妆图作为参考图（图生图模式），保证与已有定妆的一致性。
"""

import torch

from ..api import (
    AgnesClient,
    get_api_key,
    IMAGE_MODEL,
    AVAILABLE_IMAGE_MODELS,
    NEW_IMAGE_MODELS,
    pil_to_tensor,
    tensor_to_pil,
)

# 三视图固定模板（与用户规格一致：正面→侧面→背面 并排、全身、正交、A-pose、纯白背景）
TURNAROUND_TEMPLATE = (
    "{character_desc}\n\n"
    "Character turnaround sheet, character reference sheet: the same single character "
    "shown in three orthographic views arranged side by side from left to right: "
    "front view, side view (profile), back view.\n"
    "Full body complete display, orthographic views, no perspective distortion, "
    "consistent character proportions, consistent costume and hairstyle details, "
    "natural standing pose, A-pose, pure white background, clean line art, "
    "flat clean colors, high resolution, sharp details."
)

# 三视图推荐横向画幅
ASPECT_RATIOS = ["1:1", "4:3", "3:2", "16:9", "21:9"]
QUALITIES = ["1K", "2K", "3K", "4K"]


class AgnesNovelCharacterTurnaround:
    """生成角色三视图设定图（正面/侧面/背面并排）"""

    DESCRIPTION = "角色三视图设定图：同一角色正面/侧面/背面并排，全身正交视图、细节一致（可选参考图保持一致性）"

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "resolution", "final_prompt")
    RETURN_LABELS = ("三视图", "分辨率", "最终提示词")
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
                "character_desc": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "角色名 + 外貌/服装描述，例如：\n白奕，20岁青年剑修，黑色长发束高马尾，白衣黑边长剑袍，左手持剑",
                    "tooltip": "角色名称与外貌、服装、道具描述（越具体，三视图细节越一致）",
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key，留空自动加载",
                }),
                "model": (AVAILABLE_IMAGE_MODELS, {
                    "default": IMAGE_MODEL,
                    "tooltip": "图像生成模型（agnes-image-2.5-flash 支持 1K-4K 档位）",
                }),
                "quality": (QUALITIES, {
                    "default": "2K",
                    "tooltip": "画质档位：2K 性价比最高，4K 细节最清晰",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "21:9",
                    "tooltip": "画面比例，三视图推荐宽幅（21:9 / 16:9），避免三个视图被裁切",
                }),
            },
            "optional": {
                "reference_image": ("IMAGE", {
                    "tooltip": "可选：角色定妆图/已有角色图。连接后走图生图模式，三视图与参考角色保持一致",
                }),
                "extra_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "额外的风格/质量补充词...",
                    "tooltip": "追加在提示词末尾的补充要求（可选）",
                }),
            },
        }

    def generate(
        self,
        base_url: str = "",
        character_desc: str = "",
        api_key: str = "",
        model: str = IMAGE_MODEL,
        quality: str = "2K",
        aspect_ratio: str = "21:9",
        reference_image=None,
        extra_prompt: str = "",
    ):
        character_desc = (character_desc or "").strip()
        if not character_desc:
            black = torch.zeros(1, 512, 512, 3)
            return (black, "", "[Error: 角色描述为空]")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            black = torch.zeros(1, 512, 512, 3)
            return (black, "", "[Error: API key is required. Get a free key at https://platform.agnes-ai.cn/]")

        prompt = TURNAROUND_TEMPLATE.format(character_desc=character_desc)
        if extra_prompt.strip():
            prompt += "\n" + extra_prompt.strip()

        # 尺寸：新接口档位 + ratio；旧接口 WxH
        if model in NEW_IMAGE_MODELS:
            size_arg, ratio_arg = quality.upper(), aspect_ratio
            w, h = 2048, 512  # 占位尺寸（仅错误黑图用）
        else:
            size_arg = "2048x768" if aspect_ratio in ("21:9", "16:9") else "1024x1024"
            ratio_arg = None
            w, h = (2048, 768) if aspect_ratio in ("21:9", "16:9") else (1024, 1024)

        print(f"\n[Agnes Turnaround] 角色三视图生成: {character_desc[:40]}...")
        print(f"  模型: {model}, 档位: {quality}, 比例: {aspect_ratio}, 参考图: {'有' if reference_image is not None else '无'}")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            ref_imgs = [tensor_to_pil(reference_image)] if reference_image is not None else None
            mode = "img2img" if ref_imgs else "text2img"

            if model in NEW_IMAGE_MODELS:
                pil_images = client.generate_image(
                    prompt=prompt,
                    mode=mode,
                    reference_images=ref_imgs,
                    size=size_arg,
                    ratio=ratio_arg,
                    n=1,
                    model=model,
                )
            else:
                pil_images = client.generate_image(
                    prompt=prompt,
                    mode=mode,
                    reference_images=ref_imgs,
                    size=size_arg,
                    n=1,
                    model=model,
                )

            if not pil_images:
                black = torch.zeros(1, h, w, 3)
                return (black, size_arg, "[Error: 无返回图像]")

            img = pil_images[0]
            if img.mode != "RGB":
                img = img.convert("RGB")
            img_tensor = pil_to_tensor(img)

            print(f"[Agnes Turnaround] 生成成功: {img.size[0]}x{img.size[1]}")
            return (img_tensor, f"{img.size[0]}x{img.size[1]}", prompt)

        except Exception as e:
            print(f"[Agnes Turnaround] 失败: {e}")
            black = torch.zeros(1, h, w, 3)
            return (black, "", f"[Error] {e}")


NODE_CLASS_MAPPINGS = {"AgnesNovelCharacterTurnaround": AgnesNovelCharacterTurnaround}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelCharacterTurnaround": "📐 Agnes 角色三视图设定图"}
