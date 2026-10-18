"""
Agnes 视频生成节点
使用 Agnes Video API (agnes-video-v2.0)
已修复超时问题：使用 video_id 轮询替代 task_id
"""
import requests
import torch
import numpy as np
from PIL import Image
import io
import os
import time
import folder_paths
from ..api import (
    AgnesClient,
    get_api_key,
    BASE_URL,
    VIDEO_MODEL,
    VIDEO_MAX_WAIT,
    VIDEO_POLL_INTERVAL,
    NEW_VIDEO_MODELS,
    tensor_to_pil,
)


class AgnesVideoGen:
    """使用 Agnes AI 生成视频"""
    
    DESCRIPTION = "根据提示词或参考图片生成视频，支持多种时长、画质和宽高比选项"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入视频描述（可选）...",
                    "tooltip": "视频描述文本，如果提供图片则优先使用图片生成视频"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key"
                }),
                "model": ("STRING", {
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型，推荐使用 agnes-video-v2.0"
                }),
                "num_frames": ("INT", {
                    "default": 121,
                    "min": 81,
                    "max": 441,
                    "step": 8,
                    "tooltip": "视频帧数，121 帧 ≈ 5 秒 @ 24fps，可调节视频时长"
                }),
                "frame_rate": ("INT", {
                    "default": 24,
                    "min": 8,
                    "max": 60,
                    "tooltip": "视频帧率，24fps 为标准电影帧率"
                }),
                "quality": (["1K", "2K"], {
                    "default": "1K",
                    "tooltip": "画质等级（仅旧接口 agnes-video-v2.0 生效；新接口 agnes-video-2.5-flash 固定 720P）"
                }),
                "aspect_ratio": (["16:9", "9:16", "1:1", "4:3", "3:4"], {
                    "default": "16:9",
                    "tooltip": "宽高比：16:9=横屏视频，9:16=竖屏短视频，1:1=方形"
                }),
            },
            "optional": {
                "image": ("IMAGE", {
                    "tooltip": "参考图片（可选），连接图像生成节点的输出"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml）"
                }),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING",)
    RETURN_NAMES = ("video", "video_id", "task_id",)
    RETURN_LABELS = ("视频文件路径", "视频 ID", "任务 ID")
    FUNCTION = "generate"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "video" in kwargs:
            extra["video"] = {"description": "生成的视频文件保存路径"}
        if "video_id" in kwargs:
            extra["video_id"] = {"description": "视频任务的唯一标识符"}
        if "task_id" in kwargs:
            extra["task_id"] = {"description": "API 返回的任务 ID"}
        return extra

    # 宽高映射
    SIZE_MAP = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1024, 1024),
        "4:3": (1365, 1024),
        "3:4": (1024, 1365),
    }

    def generate(self, prompt, api_key, model, num_frames, frame_rate, quality, aspect_ratio, image=None, base_url=""):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err_msg = "[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]"
            return ("", "", err_msg)
        new_model = model in NEW_VIDEO_MODELS
        print(f"\n[Agnes Video] 开始生成...")
        print(f"Prompt: {prompt[:80]}...")
        if new_model:
            print(f"Model: {model}, 时长≈{min(12, max(4, int(round(num_frames / frame_rate)))) if frame_rate else 5}s, 比例: {aspect_ratio}, 固定 720P")
        else:
            print(f"Frames: {num_frames}, FPS: {frame_rate}, Ratio: {aspect_ratio}, Quality: {quality}")

        # 旧接口才需要计算 WxH 尺寸；新接口固定 720P + aspect_ratio
        width, height = 1920, 1080
        if not new_model:
            width, height = self.SIZE_MAP.get(aspect_ratio, (1920, 1080))
            if quality == "2K":
                width *= 2
                height *= 2

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            output_dir = os.path.join(folder_paths.get_output_directory(), "agnes_videos")

            # 提交任务（客户端内部完成轮询 + 下载 + 保存）
            print("[Agnes Video] 提交任务...")
            if new_model:
                result = client.generate_video(
                    prompt=prompt,
                    model=model,
                    mode="img2video" if image is not None else "text2video",
                    reference_images=[tensor_to_pil(image)] if image is not None else None,
                    seconds=min(12, max(4, int(round(num_frames / frame_rate)))) if frame_rate else None,
                    aspect_ratio=aspect_ratio,
                    max_wait=VIDEO_MAX_WAIT,
                    output_dir=output_dir,
                    return_ids=True,
                )
            else:
                result = client.generate_video(
                    prompt=prompt,
                    model=model,
                    num_frames=num_frames,
                    frame_rate=frame_rate,
                    size=f"{width}x{height}",
                    max_wait=VIDEO_MAX_WAIT,
                    output_dir=output_dir,
                    return_ids=True,
                )
            save_path, task_id, video_id = result

            print(f"[Agnes Video] 生成完成: {save_path}")
            print(f"  video_id: {video_id}")
            print(f"  task_id: {task_id}")

            # 返回视频路径和 ID
            return (save_path, video_id, task_id)

        except Exception as e:
            print(f"[Agnes Video] 失败: {e}")
            return ("", "", str(e))


NODE_CLASS_MAPPINGS = {"AgnesVideoGen": AgnesVideoGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoGen": "🎬 Agnes 视频生成"}
