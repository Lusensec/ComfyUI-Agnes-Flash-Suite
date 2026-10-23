# -*- coding: utf-8 -*-
"""
Agnes 关键帧生视频（图生视频）节点
===================================
使用 Agnes 视频生成模型（Agnes Video 2.5-flash），从关键帧生成视频
（keyframe 首尾帧模式：首帧必接，尾帧可选；接尾帧=首尾帧过渡，不接=仅按首帧生成）。
4-12 秒时长直控（seconds 参数，完整体验）+ 固定 720P + 宽高比选择。

多图参考（最多 5 张）/ 音频参考（最多 3 段）请改用「Agnes 参考视频生成」
节点（nodes/video_reference.py，reference 模式）。

异步接口 + 轮询，耗时可达数分钟。
输出：MP4 保存到 ComfyUI 的 output/agnes_videos/ 目录。
"""

import os
from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    VIDEO_MODEL,
    tensor_to_pil,
)
from ._output_docs import OutputDocsMixin

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

# 输出分辨率（Agnes 视频接口固定 720P；参数保留在节点上供展示与选择）
RESOLUTIONS = ["720P"]

# 视频时长（秒）
SECONDS_MIN = 4
SECONDS_MAX = 12
SECONDS_DEFAULT = 5

# 尝试获取 ComfyUI 的输出目录（ComfyUI 运行环境内可用）
_COMFYUI_OUTPUT_DIR = None


def video_size_label(aspect_ratio: str) -> str:
    """720P 分辨率标注：按 aspect_ratio 给出像素（16:9=1280×720，9:16=720×1280）；
    其他比例由服务端自动映射，只标 720P。"""
    if aspect_ratio == "16:9":
        return "1280x720 (720P)"
    if aspect_ratio == "9:16":
        return "720x1280 (720P)"
    return "720P（服务端自动映射）"


def _get_output_dir() -> str:
    """获取 ComfyUI 的视频输出目录（保存视频文件用）。"""
    global _COMFYUI_OUTPUT_DIR
    if _COMFYUI_OUTPUT_DIR is not None:
        return _COMFYUI_OUTPUT_DIR

    try:
        from folder_paths import get_output_directory
        base = get_output_directory()
    except ImportError:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")

    _COMFYUI_OUTPUT_DIR = os.path.join(base, "agnes_videos")
    return _COMFYUI_OUTPUT_DIR


# 探测视频输出类型（优先级：comfy_api VIDEO > VHS > STRING）。
_VIDEO_OUTPUT_TYPE = "STRING"
_VIDEO_MODE = "string"  # 三种输出模式："comfy_api" | "vhs" | "string"

# 1. 尝试原生 VIDEO 类型（comfy_api，随 ComfyUI v1.7+ 自带）
try:
    from comfy_api.latest import InputImpl as _ApiInput
    if hasattr(_ApiInput, "VideoFromFile"):
        _VIDEO_OUTPUT_TYPE = "VIDEO"
        _VIDEO_MODE = "comfy_api"
except Exception:
    pass

# 2. 回退到 VHS 的 VHS_VIDEOINFO（已安装视频Helper时）
if _VIDEO_MODE == "string":
    try:
        import nodes as _comfy_nodes
        if hasattr(_comfy_nodes, "NODE_CLASS_MAPPINGS"):
            if "VHS_VIDEOINFO" in str(_comfy_nodes.NODE_CLASS_MAPPINGS):
                _VIDEO_OUTPUT_TYPE = "VHS_VIDEOINFO"
                _VIDEO_MODE = "vhs"
    except Exception:
        pass


class AgnesNovelImageToVideo(OutputDocsMixin):
    """Agnes 关键帧生视频（图生视频）节点：首帧必接，尾帧可选；4-12 秒 720P。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING",)
    RETURN_NAMES = ("video", "resolution",)
    RETURN_LABELS = ('视频', '分辨率')
    OUTPUT_DOCS = {
        "video": "生成的视频（MP4 保存到 ComfyUI output/agnes_videos/；输出类型随环境为 VIDEO/VHS_VIDEOINFO/路径字符串），可连接 SaveVideo 预览",
        "resolution": "视频分辨率标注：固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）",
    }
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "label": "首帧",
                    "tooltip": "关键帧·首帧（必接）：可再接尾帧做首尾帧过渡；可直连 Agnes 分镜图批量 的 image_N 关键帧；多图/音频参考请用「Agnes 参考视频生成」节点"
                }),
                "prompt": ("STRING", {
                    "label": "提示词",
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入运动描述（建议英文），例如：Smooth camera pan with gentle motion...",
                    "tooltip": "描述想要的动画/运动效果（建议英文提示词，可连 Agnes 视频提示词生成 的 video_prompt 输出；mode 选 keyframe）",
                }),
                "base_url": ("STRING", {
                    "label": "请求地址",
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
                "api_key": ("STRING", {
                    "label": "API Key",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key（留空则跟随全局配置：环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）",
                }),
                "model": ([VIDEO_MODEL], {
                    "label": "模型",
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型：Agnes Video 2.5-flash（keyframe 关键帧模式，4-12 秒 / 720P）",
                }),
                "resolution": (RESOLUTIONS, {
                    "label": "分辨率",
                    "default": "720P",
                    "tooltip": "输出分辨率：Agnes 视频接口固定 720P（参数保留供展示与选择，目前仅此一项）",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "label": "宽高比",
                    "default": "16:9",
                    "tooltip": "画面宽高比（宽:高）：16:9 横屏 / 9:16 竖屏；API 文档列 16:9/9:16（可选，缺省服务端自动处理），其他比例自动就近映射",
                }),
                "seconds": ("INT", {
                    "label": "时长（秒）",
                    "default": SECONDS_DEFAULT,
                    "min": SECONDS_MIN,
                    "max": SECONDS_MAX,
                    "step": 1,
                    "tooltip": "视频时长（秒，4-12 直控）：一镜一主动作，时长内不换场景不切镜；与 Agnes 视频提示词生成 的 duration 保持一致",
                }),
                "seed": ("INT", {
                    "label": "随机种子",
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "随机种子（0=每次随机，固定值可复现结果）；随机请用输入框旁的骰子按钮（本节点已禁用前端自动附加的「生成后控制」英文下拉）",
                }),
                "max_wait_seconds": ("INT", {
                    "label": "轮询超时",
                    "default": 600,
                    "min": 60,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "视频生成轮询最长等待时间（秒，生成耗时可达数分钟）",
                }),
            },
            "optional": {
                "end_frame_image": ("IMAGE", {
                    "label": "尾帧（可选）",
                    "tooltip": "关键帧·尾帧（可选）：接了=首尾帧过渡（image→image 运动）；不接=仅按首帧生成。"
                               "多图/音频参考请用「Agnes 参考视频生成」节点"
                }),
            },
        }

    def generate(
        self,
        image=None,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = VIDEO_MODEL,
        resolution: str = "720P",
        aspect_ratio: str = "16:9",
        seconds: int = SECONDS_DEFAULT,
        seed: int = 0,
        max_wait_seconds: int = 600,
        end_frame_image=None,
    ) -> Tuple:
        if image is None:
            return _error("关键帧首帧未连接：image 输入必接（可连 Agnes 分镜图批量 的 image_N 或 图像生成 的 image）")

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return _error("缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置")
        if not prompt.strip():
            return _error("提示词为空：请描述运动效果")

        # 分辨率固定 720P（widget 展示用）；输出标注按宽高比给出像素
        size = video_size_label(aspect_ratio)
        output_dir = _get_output_dir()

        try:
            has_end_frame = end_frame_image is not None
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            # keyframe 关键帧模式（首帧必填；接尾帧=首尾帧过渡，不接=仅首帧）
            video_path = client.generate_video(
                prompt=prompt.strip(),
                mode="keyframe",
                first_frame=tensor_to_pil(image),
                last_frame=tensor_to_pil(end_frame_image) if has_end_frame else None,
                model=model,
                seconds=seconds,
                aspect_ratio=aspect_ratio,
                seed=seed if seed > 0 else None,
                max_wait=max_wait_seconds,
                output_dir=output_dir,
            )

            if video_path:
                return _make_result(video_path, size)
            return _error("未返回视频", size)

        except Exception as e:
            return _error(str(e), size)


# ---- 结果构建函数（视频节点共享） ----

def _make_result(video_path: str, size: str) -> Tuple:
    """按可用输出类型构建 (video_output, resolution) 结果元组。"""
    filename = os.path.basename(video_path)

    if _VIDEO_MODE == "comfy_api":
        video_output = _ApiInput.VideoFromFile(video_path)
        return (video_output, size)

    if _VIDEO_MODE == "vhs":
        return ({"filename": filename, "subfolder": "agnes_videos", "type": "output"}, size)

    return (video_path, size)


def _error(msg: str, size: str = "") -> Tuple:
    """构建错误结果。comfy_api VIDEO 模式下直接抛错（返回字符串会令 SaveVideo 崩溃）。"""
    text = f"[错误] {msg}"
    if _VIDEO_MODE == "comfy_api":
        raise RuntimeError(text)
    if _VIDEO_MODE == "vhs":
        return ({"filename": "", "subfolder": "", "type": "output"}, text)
    return (text, text) if not size else (text, size)

NODE_CLASS_MAPPINGS = {"AgnesNovelImageToVideo": AgnesNovelImageToVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelImageToVideo": "🎬 Agnes 关键帧生视频"}
