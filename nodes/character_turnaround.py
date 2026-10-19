# -*- coding: utf-8 -*-
"""
Agnes 三视图生成节点
====================
纯出图节点：**不使用任何内置提示词模板**——直接用 subject_desc 输入的
完整三视图提示词生成三视图设定图（turnaround sheet）。

完整三视图提示词推荐由 Agnes 三视图提示词生成 节点输出（原始描述 →
LLM 合并三视图构图指令 + 纯白背景平光无阴影规格 + 质量尾词，
输出对用户可见、可手工修改优化后再填入本节点）。

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


# 三视图推荐横向画幅
ASPECT_RATIOS = ["1:1", "4:3", "3:2", "16:9", "21:9"]
QUALITIES = ["1K", "2K", "3K", "4K"]


class AgnesSubjectTurnaround(OutputDocsMixin):
    """生成主体三视图设定图（角色/物品/场景/载具/通用，正视图并排）"""

    DESCRIPTION = "三视图生成：直接用输入的完整三视图提示词出图（无内置模板，提示词推荐由 Agnes 三视图提示词生成 节点输出），可选参考图保持一致"

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING",)
    RETURN_NAMES = ("image", "resolution", "final_prompt")
    RETURN_LABELS = ("三视图", "分辨率", "最终提示词")
    OUTPUT_DOCS = {
        "image": "三视图设定图张量（三个视图并排），可连接 SaveImage 存档或作为后续生成的参考图",
        "resolution": "三视图实际输出分辨率（WxH）",
        "final_prompt": "实际使用的完整提示词（subject_desc + extra_prompt 补充词），可复制复用或微调",
    }
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "subject_desc": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "完整三视图提示词（推荐连 Agnes 三视图提示词生成 的输出）：\nSu Chen, 20-year-old sword cultivator, three orthographic views side by side: front, side, back, full body, pure white background, even flat lighting...",
                    "tooltip": "完整三视图提示词（无内置模板，出什么图由这段提示词决定）：推荐连 Agnes 三视图提示词生成 节点输出，或手动粘贴/手工修改后的提示词",
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

        prompt = subject_desc
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

        print(f"\n[Agnes 三视图] 三视图生成: {subject_desc[:40]}...")
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
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesSubjectTurnaround": "📐 Agnes 三视图生成"}
