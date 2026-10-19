# -*- coding: utf-8 -*-
"""
Agnes 三视图生成节点
====================
生成任意主体的三视图设定表（turnaround sheet）：同一主体的
正面 / 侧面 / 背面（场景为 正面 / 侧面 / 俯视）三个视图从左到右并排排列，
正交视图、比例与细节保持一致。

主体类型（subject_type）：
- 角色：全身正交视图、A-pose、服装发型细节一致
- 物品/道具：产品设定表，结构材质细节一致
- 场景：场景概念表（正立面/侧立面/俯视图）
- 载具：整车设定表，钣金细节一致
- 通用：任意主体的通用三视图模板

可选连接参考图（定妆图/已有设定图）走图生图模式，保证与已有资产一致。
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
from ._output_docs import OutputDocsMixin

# 各主体类型的三视图固定模板（与用户规格一致：三视图并排、正交、细节一致、纯白背景）
_TURNAROUND_TEMPLATES = {
    "角色": (
        "{subject_desc}\n\n"
        "Character turnaround sheet, character reference sheet: the same single character "
        "shown in three orthographic views arranged side by side from left to right: "
        "front view, side view (profile), back view.\n"
        "Full body complete display, orthographic views, no perspective distortion, "
        "consistent character proportions, consistent costume and hairstyle details, "
        "natural standing pose, A-pose, pure white background, clean line art, "
        "flat clean colors, high resolution, sharp details."
    ),
    "物品/道具": (
        "{subject_desc}\n\n"
        "Item design sheet, product reference sheet: the same single item "
        "shown in three orthographic views arranged side by side from left to right: "
        "front view, side view, back view.\n"
        "Complete display of the whole item, orthographic views, no perspective distortion, "
        "consistent proportions, consistent structure and material details, "
        "plain neutral white background, clean line art, high resolution, sharp details."
    ),
    "场景": (
        "{subject_desc}\n\n"
        "Scene concept sheet, environment reference sheet: the same scene "
        "shown in three views arranged side by side from left to right: "
        "front elevation, side elevation, top-down plan view.\n"
        "Orthographic views, no perspective distortion, consistent layout, "
        "consistent architecture/structure and material details, "
        "clean line art, flat clean colors, high resolution, sharp details."
    ),
    "载具": (
        "{subject_desc}\n\n"
        "Vehicle turnaround sheet, vehicle reference sheet: the same single vehicle "
        "shown in three orthographic views arranged side by side from left to right: "
        "front view, side view, back view.\n"
        "Full vehicle complete display, orthographic views, no perspective distortion, "
        "consistent proportions, consistent body panels, trim and detail design, "
        "pure white background, clean line art, high resolution, sharp details."
    ),
    "通用": (
        "{subject_desc}\n\n"
        "Turnaround sheet, reference sheet: the same single subject "
        "shown in three orthographic views arranged side by side from left to right: "
        "front view, side view, back view.\n"
        "Complete display, orthographic views, no perspective distortion, "
        "consistent proportions and details, pure white background, clean line art, "
        "high resolution, sharp details."
    ),
}

SUBJECT_TYPES = list(_TURNAROUND_TEMPLATES.keys())

# 三视图推荐横向画幅
ASPECT_RATIOS = ["1:1", "4:3", "3:2", "16:9", "21:9"]
QUALITIES = ["1K", "2K", "3K", "4K"]


class AgnesSubjectTurnaround(OutputDocsMixin):
    """生成主体三视图设定图（角色/物品/场景/载具/通用，正视图并排）"""

    DESCRIPTION = "三视图生成：任意主体（角色/物品/场景/载具）正面/侧面/背面并排设定表，正交视图、细节一致（可选参考图保持一致性）"

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "resolution", "final_prompt")
    RETURN_LABELS = ("三视图", "分辨率", "最终提示词")
    OUTPUT_DOCS = {
        "image": "三视图设定图张量（三个视图并排），可连接 SaveImage 存档或作为后续生成的参考图",
        "resolution": "三视图实际输出分辨率（WxH）",
        "final_prompt": "最终拼接的完整提示词（主体描述 + 该类型三视图模板 + 补充词），可复制复用或微调",
    }
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "subject_type": (SUBJECT_TYPES, {
                    "default": "角色",
                    "tooltip": "主体类型：决定三视图提示词模板（角色=全身A-pose / 物品=产品设定 / 场景=立面+俯视 / 载具=整车设定 / 通用=任意主体）",
                }),
                "subject_desc": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "主体名称 + 外观描述，例如：\n白奕，20岁青年剑修，黑色长发束高马尾，白衣黑边长剑袍，左手持剑",
                    "tooltip": "主体名称与外观、材质/结构等描述（越具体，三视图细节越一致）",
                }),
                "base_url": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
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
                    "tooltip": "可选：定妆图/已有设定图。连接后走图生图模式，三视图与参考保持一致",
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
        subject_type: str = "角色",
        subject_desc: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = IMAGE_MODEL,
        quality: str = "2K",
        aspect_ratio: str = "21:9",
        reference_image=None,
        extra_prompt: str = "",
    ):
        subject_desc = (subject_desc or "").strip()
        if not subject_desc:
            black = torch.zeros(1, 512, 512, 3)
            return (black, "", "[Error: 主体描述为空]")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            black = torch.zeros(1, 512, 512, 3)
            return (black, "", "[Error: API key is required. Get a free key at https://platform.agnes-ai.cn/]")

        if subject_type not in _TURNAROUND_TEMPLATES:
            subject_type = "通用"
        prompt = _TURNAROUND_TEMPLATES[subject_type].format(subject_desc=subject_desc)
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

        print(f"\n[Agnes 三视图] {subject_type}三视图生成: {subject_desc[:40]}...")
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

            print(f"[Agnes 三视图] 生成成功: {img.size[0]}x{img.size[1]}")
            return (img_tensor, f"{img.size[0]}x{img.size[1]}", prompt)

        except Exception as e:
            print(f"[Agnes 三视图] 失败: {e}")
            black = torch.zeros(1, h, w, 3)
            return (black, "", f"[Error] {e}")


NODE_CLASS_MAPPINGS = {"AgnesSubjectTurnaround": AgnesSubjectTurnaround}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesSubjectTurnaround": "Agnes 三视图生成"}
