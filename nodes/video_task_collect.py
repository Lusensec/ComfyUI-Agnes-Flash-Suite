# -*- coding: utf-8 -*-
"""
Agnes 视频任务收取节点（异步两段式·收取段，单任务）
=====================================================
输入 1 路 task_url（直连 Agnes 视频任务提交 的 task_url 输出；完整轮询 URL
自带域名，跨域名提交的任务同样可查），节点内轮询查询任务状态：

  completed  → 自动下载 mp4 到 ComfyUI output/agnes_videos/，
               video 输出=本地路径，status 输出=服务端视频 URL；
  failed     → video 输出=空，status 输出=Agnes 服务端错误响应内容；
  processing → 到 timeout 仍生成中（不算失败）：video=空，
               status 提示可再次右键运行本节点继续查（任务还在服务端）。

轮询节奏与 文生视频 一致：首查前等 60s（任务排队期），之后每 5s 一次；
下载自动 3 次重试（2/5/10 秒），URL 仍在有效期内可手动抢救。
"""

import os
from typing import Tuple

from ..api import AgnesClient, get_api_key
from ._output_docs import OutputDocsMixin

# 输出目录：与 文生视频 节点一致（ComfyUI output/agnes_videos/）
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


class AgnesVideoTaskCollect(OutputDocsMixin):
    """Agnes 视频任务收取：单路 task_url 轮询查询（URL 自带域名），completed 自动下载，输出 video 本地路径 + status。"""

    DESCRIPTION = "视频任务异步收取（两段式第二段，单任务）：输入 1 路 task_url（直连 视频任务提交 的 task_url 输出；完整轮询 URL 自带域名，跨域名提交的任务同样可查）；节点内轮询查询（首查前 60s、之后每 5s），completed 自动下载 mp4 到 output/agnes_videos/（3 次重试）；输出 2 路：video（本地路径，未完成/失败=空）+ status（completed=服务端视频 URL；failed=Agnes 服务端错误响应内容；processing=到 timeout 未完成，可再次运行本节点继续查）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("video", "status",)
    RETURN_LABELS = ("视频（本地路径）", "状态")
    OUTPUT_DOCS = {
        "video": "MP4 本地路径（ComfyUI output/agnes_videos/）；任务未完成/失败/未连接输入时为空。字符串路径可接支持文件路径的视频预览节点，或在 output 目录直接查看/下载",
        "status": "任务状态：completed=服务端视频 URL（有效期内可浏览器直接播放/下载）；failed=Agnes 服务端错误响应内容（含任务级 failed 与下载失败诊断）；processing=到轮询超时任务未完成（可再次右键运行本节点继续查询）；empty=未连接 task_url",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_url": ("STRING", {
                    "label": "轮询 URL",
                    "multiline": True,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/agnesapi?video_id=…&model_name=agnes-video-2.5-flash",
                    "tooltip": "完整轮询 URL：直连 Agnes 视频任务提交 的 task_url 输出（含域名，跨域名提交的任务也能查）；留空=整节点跳过（status 输出 empty）",
                }),
                "api_key": ("STRING", {
                    "label": "API Key",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key：轮询查询需 Bearer 鉴权，留空则跟随全局配置（API Key 配置节点/环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）；域名已在 task_url 里，无需再填请求地址",
                }),
                "timeout": ("INT", {
                    "label": "轮询超时",
                    "default": 1800,
                    "min": 60,
                    "max": 7200,
                    "step": 60,
                    "tooltip": "本节点最长等待（秒，默认 1800=30 分钟）：到点仍生成中=processing（不算失败），再次右键运行本节点即继续查（任务还在服务端）；视频一般 3-10 分钟出片，默认 30 分钟通常一趟收完",
                }),
            },
        }

    def generate(
        self,
        task_url: str = "",
        api_key: str = "",
        timeout: int = 1800,
    ) -> Tuple:
        url = str(task_url or "").strip()
        if not url:
            return ("", "empty: 未连接 task_url 输入（可直连 Agnes 视频任务提交 的 task_url 输出）")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("", "failed: 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）")

        client = AgnesClient(api_key)
        result = client.collect_video_task(url, timeout=timeout, output_dir=_get_output_dir())
        state = result["status"]
        if state == "completed":
            print(f"[Agnes 视频任务收取] 完成：{result['save_path']}（服务端 URL: {result['video_url'][:80]}…）")
            return (result["save_path"], f"completed: {result['video_url']}")
        if state == "failed":
            print(f"[Agnes 视频任务收取] [错误] {result['error']}")
            return ("", f"failed: {result['error']}")
        print(f"[Agnes 视频任务收取] 生成中（{result['error'].split('，')[0]}），可再次运行本节点继续查询")
        return ("", f"processing: {result['error']}")


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskCollect": AgnesVideoTaskCollect}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskCollect": "📥 Agnes 视频任务收取"}
