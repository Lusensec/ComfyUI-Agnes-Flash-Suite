"""视频落盘目录公共助手（中性模块，避免 text2video ↔ video_task_collect 循环导入）。

_get_output_dir: ComfyUI 输出目录/agnes_videos/（folder_paths 取根，取不到回退
套件上级 output/）。_resolve_save_dir: 「保存目录」widget 解析（空=默认目录；
非空=绝对或相对 ComfyUI 根目录，自动创建，失败回退默认）。
"""

import os

_COMFYUI_OUTPUT_DIR = None


def _get_output_dir() -> str:
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


def _resolve_save_dir(save_dir) -> str:
    """视频落盘目录解析（「保存目录」widget）：
    留空/None = 默认 ComfyUI 输出目录/agnes_videos/（与旧行为一致）；
    非空 = 指定目录（绝对路径，或相对 ComfyUI 根目录），自动创建，
    创建失败回退默认目录（不阻断队列）。"""
    s = str(save_dir or "").strip()
    if not s:
        return _get_output_dir()
    if not os.path.isabs(s):
        # 相对路径基准 = ComfyUI 根目录（nodes/ → 套件 → custom_nodes → ComfyUI）
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        s = os.path.join(root, s)
    s = os.path.normpath(s)
    try:
        os.makedirs(s, exist_ok=True)
    except OSError as e:
        print(f"[Agnes] 保存目录创建失败（{s}：{e}），回退默认 output/agnes_videos/")
        return _get_output_dir()
    return s
