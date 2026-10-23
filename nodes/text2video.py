"""
Agnes 文生视频节点
==================
使用 Agnes AI 视频生成模型，根据文本描述生成视频。
异步接口 + 轮询，耗时可达数分钟。

新接口 2.5-flash 固定 720P（API 无 size 参数，分辨率输出按 720P 标注）；
旧接口 v2.0 固定 1K 档位映射 WxH。支持宽高比选择。

输出：MP4 保存到 ComfyUI 的 output/agnes_videos/ 目录，
用户可在 Web UI 中预览和下载。
"""

import os
from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    VIDEO_MODEL,
    AVAILABLE_VIDEO_MODELS,
    DEFAULT_VIDEO_FRAMES,
    DEFAULT_VIDEO_FPS,
    NEW_VIDEO_MODELS,
)
from ._output_docs import OutputDocsMixin

# 画质档位 → 短边像素
QUALITY_MAP = {
    "1K": 1024,
    "2K": 2048,
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

# 尝试获取 ComfyUI 的输出目录（ComfyUI 运行环境内可用）
_COMFYUI_OUTPUT_DIR = None


def compute_size(quality: str, aspect_ratio: str) -> str:
    """
    根据画质档位与宽高比计算 WxH 像素尺寸字符串。
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


def new_model_size_label(aspect_ratio: str) -> str:
    """新接口 2.5-flash：API 无 size 参数，固定 720P。
    按 API 文档 aspect_ratio 两档给出像素（16:9=1280×720，9:16=720×1280）；
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


class AgnesNovelTextToVideo(OutputDocsMixin):
    """Agnes AI 文生视频节点：按文本描述直接生成视频。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING",)
    RETURN_NAMES = ("video", "resolution",)
    RETURN_LABELS = ('视频', '分辨率')
    OUTPUT_DOCS = {
        "video": "生成的视频（MP4 保存到 ComfyUI output/agnes_videos/；输出类型随环境为 VIDEO/VHS_VIDEOINFO/路径字符串），可连接 SaveVideo 预览",
        "resolution": "视频目标尺寸：新接口 2.5-flash 固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）；旧接口 v2.0 固定 1K 档位映射 WxH",
    }
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入视频描述（建议英文），例如：A cinematic drone shot flying over a misty forest at sunrise...",
                    "tooltip": "要生成视频的文本描述（建议英文提示词）",
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
                "model": (AVAILABLE_VIDEO_MODELS, {
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型：agnes-video-2.5-flash（4-12s/720P，API 无 size 参数）/ agnes-video-v2.0（帧数模式，固定 1K 档位映射 WxH）",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "16:9",
                    "tooltip": "输出宽高比（宽:高）：如 16:9 宽屏、9:16 竖屏；新接口 2.5-flash 不支持的比例自动就近映射",
                }),
                "num_frames": ("INT", {
                    "default": DEFAULT_VIDEO_FRAMES,
                    "min": 9,
                    "max": 441,
                    "step": 8,
                    "tooltip": "帧数（旧接口必须 8n+1，121≈5s@24fps，241≈10s）；新接口 2.5-flash 按 帧数/帧率 换算成 4-12 秒时长",
                }),
                "frame_rate": ("INT", {
                    "default": DEFAULT_VIDEO_FPS,
                    "min": 8,
                    "max": 60,
                    "step": 1,
                    "tooltip": "帧率：旧接口传给 API；新接口 agnes-video-2.5-flash 无 frame_rate 参数，仅用于把帧数换算成 4-12 秒时长",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "tooltip": "随机种子（Agnes 视频 API 支持 seed；0=每次随机，固定值可复现结果）",
                }),
                "max_wait_seconds": ("INT", {
                    "default": 600,
                    "min": 60,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "视频生成轮询最长等待时间（秒）",
                }),
            },
        }

    def generate(
        self,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = VIDEO_MODEL,
        aspect_ratio: str = "16:9",
        num_frames: int = DEFAULT_VIDEO_FRAMES,
        frame_rate: int = DEFAULT_VIDEO_FPS,
        seed: int = 0,
        max_wait_seconds: int = 600,
    ) -> Tuple:
        if not prompt.strip():
            return _error("提示词为空：请描述视频内容")

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return _error("缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置")

        if model in NEW_VIDEO_MODELS:
            # 新接口 2.5-flash：API 无 size 参数，固定 720P（分辨率输出按 720P 标注，不再按画质档位瞎算）
            size = new_model_size_label(aspect_ratio)
        else:
            # 旧接口 v2.0：quality 档位下拉已移除，固定 1K 档位映射 WxH
            size = compute_size("1K", aspect_ratio)
        output_dir = _get_output_dir()

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_VIDEO_MODELS:
                # 新接口：seconds(4-12) + aspect_ratio，固定 720P
                seconds = int(round(num_frames / frame_rate)) if frame_rate else 5
                video_path = client.generate_video(
                    prompt=prompt.strip(),
                    mode="text",
                    model=model,
                    seconds=seconds,
                    aspect_ratio=aspect_ratio,
                    seed=seed if seed > 0 else None,
                    max_wait=max_wait_seconds,
                    output_dir=output_dir,
                )
            else:
                # 旧接口：num_frames/frame_rate/size(WxH)
                video_path = client.generate_video(
                    prompt=prompt.strip(),
                    mode="text2video",
                    model=model,
                    num_frames=num_frames,
                    frame_rate=frame_rate,
                    seed=seed if seed > 0 else None,
                    size=size,
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
        # Native VIDEO type: return VideoFromFile
        video_output = _ApiInput.VideoFromFile(video_path)
        return (video_output, size)

    if _VIDEO_MODE == "vhs":
        # VHS_VIDEOINFO dict
        return ({"filename": filename, "subfolder": "agnes_videos", "type": "output"}, size)

    # 字符串回退模式
    return (video_path, size)


def _error(msg: str, size: str = "") -> Tuple:
    """构建错误结果。comfy_api VIDEO 模式下直接抛错（返回字符串会令 SaveVideo 崩溃）。"""
    text = f"[错误] {msg}"
    if _VIDEO_MODE == "comfy_api":
        raise RuntimeError(text)
    if _VIDEO_MODE == "vhs":
        return ({"filename": "", "subfolder": "", "type": "output"}, text)
    return (text, text) if not size else (text, size)

NODE_CLASS_MAPPINGS = {"AgnesNovelTextToVideo": AgnesNovelTextToVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelTextToVideo": "🎞️ Agnes 文生视频"}
