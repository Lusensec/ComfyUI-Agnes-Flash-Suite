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
from ..api import AgnesClient, BASE_URL, VIDEO_MODEL, VIDEO_MAX_WAIT, VIDEO_POLL_INTERVAL


class AgnesVideoGen:
    """使用 Agnes AI 生成视频"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入视频描述..."
                }),
                "api_key": ("STRING", {
                    "default": "sk-你的Key",
                    "placeholder": "Agnes API Key"
                }),
                "model": ("STRING", {"default": VIDEO_MODEL}),
                "num_frames": ("INT", {"default": 121, "min": 81, "max": 441, "step": 8}),
                "frame_rate": ("INT", {"default": 24, "min": 8, "max": 60}),
                "quality": (["1K", "2K"], {"default": "1K"}),
                "aspect_ratio": (["16:9", "9:16", "1:1", "4:3", "3:4"], {"default": "16:9"}),
            },
            "optional": {
                "image": ("IMAGE", {"tooltip": "输入参考图片（可选）"}),
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING",)
    RETURN_NAMES = ("video", "video_id", "task_id",)
    FUNCTION = "generate"
    CATEGORY = "🎬 Agnes Novel"

    # 宽高映射
    SIZE_MAP = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1024, 1024),
        "4:3": (1365, 1024),
        "3:4": (1024, 1365),
    }

    def generate(self, prompt, api_key, model, num_frames, frame_rate, quality, aspect_ratio, image=None):
        print(f"\n[Agnes Video] 开始生成...")
        print(f"Prompt: {prompt[:80]}...")
        print(f"Frames: {num_frames}, FPS: {frame_rate}, Ratio: {aspect_ratio}, Quality: {quality}")

        # 计算尺寸
        width, height = self.SIZE_MAP.get(aspect_ratio, (1920, 1080))
        if quality == "2K":
            width *= 2
            height *= 2

        try:
            client = AgnesClient(api_key)
            
            # 提交任务
            print("[Agnes Video] 提交任务...")
            result = client.generate_video(
                prompt=prompt,
                model=model,
                num_frames=num_frames,
                frame_rate=frame_rate,
                width=width,
                height=height,
                max_wait=VIDEO_MAX_WAIT,
            )
            
            video_url = result["video_url"]
            video_id = result["video_id"]
            task_id = result["task_id"]
            
            print(f"[Agnes Video] 生成完成: {video_url}")
            print(f"  video_id: {video_id}")
            print(f"  task_id: {task_id}")
            
            # 下载视频
            video_resp = requests.get(video_url, timeout=120)
            video_bytes = video_resp.content
            
            # 保存到输出目录
            output_dir = os.path.join(folder_paths.get_output_directory(), "agnes_videos")
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = int(time.time())
            filename = f"agnes_video_{timestamp}_{video_id[:8]}.mp4"
            save_path = os.path.join(output_dir, filename)
            
            with open(save_path, "wb") as f:
                f.write(video_bytes)
            
            print(f"[Agnes Video] 已保存: {save_path}")
            
            # 返回视频路径和 ID
            return (save_path, video_id, task_id)

        except Exception as e:
            print(f"[Agnes Video] 失败: {e}")
            return ("", "", str(e))


NODE_CLASS_MAPPINGS = {"AgnesVideoGen": AgnesVideoGen}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoGen": "🎬 Agnes 视频生成"}
