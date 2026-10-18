"""
Agnes Image-to-Video Node
=========================
Generate videos from still images using Agnes AI video generation models.
Supports multi-image input for keyframe-based animation.
Uses async API with polling - can take several minutes.

Supports quality (1K/2K) and aspect ratio selection.

Output: Saves MP4 to ComfyUI's output/agnes_videos/ directory so users can
preview and download from the web UI.
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
    tensor_to_pil,
)

# Quality → short-side pixels
QUALITY_MAP = {
    "1K": 1024,
    "2K": 2048,
}

# Supported aspect ratios (width:height)
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

# Try to get ComfyUI's output directory (available inside ComfyUI runtime).
_COMFYUI_OUTPUT_DIR = None


def compute_size(quality: str, aspect_ratio: str) -> str:
    """Compute a WxH pixel size string from quality level and aspect ratio."""
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


def _get_output_dir() -> str:
    """Get ComfyUI's output directory for saving video files."""
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


# Detect video output type (priority: comfy_api VIDEO > VHS > STRING).
_VIDEO_OUTPUT_TYPE = "STRING"
_VIDEO_MODE = "string"  # "comfy_api" | "vhs" | "string"

# 1. Try native VIDEO type from comfy_api (ships with ComfyUI v1.7+)
try:
    from comfy_api.latest import InputImpl as _ApiInput
    if hasattr(_ApiInput, "VideoFromFile"):
        _VIDEO_OUTPUT_TYPE = "VIDEO"
        _VIDEO_MODE = "comfy_api"
except Exception:
    pass

# 2. Fallback to VHS_VIDEOINFO
if _VIDEO_MODE == "string":
    try:
        import nodes as _comfy_nodes
        if hasattr(_comfy_nodes, "NODE_CLASS_MAPPINGS"):
            if "VHS_VIDEOINFO" in str(_comfy_nodes.NODE_CLASS_MAPPINGS):
                _VIDEO_OUTPUT_TYPE = "VHS_VIDEOINFO"
                _VIDEO_MODE = "vhs"
    except Exception:
        pass


class AgnesNovelImageToVideo:
    """Agnes AI Image-to-Video node for ComfyUI."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING",)
    RETURN_NAMES = ("video", "resolution",)
    RETURN_LABELS = ('视频', '分辨率')
    FUNCTION = "generate"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Your Agnes AI API key",
                }),
                "image": ("IMAGE", {
                    "tooltip": "Primary input image to animate",
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Smooth camera pan with gentle motion...",
                    "tooltip": "Description of the desired animation/motion",
                }),
                "model": (AVAILABLE_VIDEO_MODELS, {
                    "default": VIDEO_MODEL,
                    "tooltip": "Video generation model",
                }),
                "quality": (["1K", "2K"], {
                    "default": "1K",
                    "tooltip": "Video quality / short-side resolution. 1K=1024px, 2K=2048px",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "default": "16:9",
                    "tooltip": "Output aspect ratio (width:height). E.g. 16:9 for widescreen, 9:16 for portrait",
                }),
                "num_frames": ("INT", {
                    "default": DEFAULT_VIDEO_FRAMES,
                    "min": 9,
                    "max": 441,
                    "step": 8,
                    "tooltip": "Number of frames (must be 8n+1). 121=~5s @24fps",
                }),
                "frame_rate": ("INT", {
                    "default": DEFAULT_VIDEO_FPS,
                    "min": 8,
                    "max": 60,
                    "step": 1,
                    "tooltip": "Frame rate in fps",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "tooltip": "Random seed (0 = random). Set to reuse for reproducible results.",
                }),
                "max_wait_seconds": ("INT", {
                    "default": 600,
                    "min": 60,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "Maximum time to wait for video generation (in seconds)",
                }),
            },
            "optional": {
                "end_frame_image": ("IMAGE", {
                    "tooltip": "Optional end frame for keyframe-based animation (image -> image transition). "
                               "新模型 agnes-video-2.5-flash：接尾帧=keyframe 首尾帧模式，不接=reference 参考图模式",
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
            },
        }

    def generate(
        self,
        api_key: str,
        image,
        prompt: str,
        model: str = VIDEO_MODEL,
        quality: str = "1K",
        aspect_ratio: str = "16:9",
        num_frames: int = DEFAULT_VIDEO_FRAMES,
        frame_rate: int = DEFAULT_VIDEO_FPS,
        seed: int = 0,
        max_wait_seconds: int = 600,
        end_frame_image=None,
        base_url: str = "",
    ) -> Tuple:
        # Runtime fallback: try config file if widget value is empty
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return _error("API key is required")
        if not prompt.strip():
            return _error("Prompt is empty")

        size = compute_size(quality, aspect_ratio)
        output_dir = _get_output_dir()

        try:
            # Collect reference images
            ref_imgs = [tensor_to_pil(image)]
            has_end_frame = end_frame_image is not None
            if has_end_frame:
                ref_imgs.append(tensor_to_pil(end_frame_image))

            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_VIDEO_MODELS:
                # 新接口：有尾帧 → keyframe 首尾帧模式；否则 reference 参考图模式
                mode_arg = "keyframe" if has_end_frame else "reference"
                seconds = int(round(num_frames / frame_rate)) if frame_rate else 5
                video_path = client.generate_video(
                    prompt=prompt.strip(),
                    mode=mode_arg,
                    reference_images=ref_imgs,
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
                    mode="img2video",
                    reference_images=ref_imgs,
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
            return _error("No video returned", size)

        except Exception as e:
            return _error(str(e), size)


# ---- Result builders (shared) ----

def _make_result(video_path: str, size: str) -> Tuple:
    """Build a (video_output, resolution) tuple based on available output type."""
    filename = os.path.basename(video_path)

    if _VIDEO_MODE == "comfy_api":
        video_output = _ApiInput.VideoFromFile(video_path)
        return (video_output, size)

    if _VIDEO_MODE == "vhs":
        return ({"filename": filename, "subfolder": "agnes_videos", "type": "output"}, size)

    return (video_path, size)


def _error(msg: str, size: str = "") -> Tuple:
    """Build an error. Raises in comfy_api VIDEO mode (string would crash SaveVideo)."""
    text = f"[Error] {msg}"
    if _VIDEO_MODE == "comfy_api":
        raise RuntimeError(text)
    if _VIDEO_MODE == "vhs":
        return ({"filename": "", "subfolder": "", "type": "output"}, text)
    return (text, text) if not size else (text, size)

NODE_CLASS_MAPPINGS = {"AgnesNovelImageToVideo": AgnesNovelImageToVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelImageToVideo": "🎬 Agnes Novel 图生视频"}
