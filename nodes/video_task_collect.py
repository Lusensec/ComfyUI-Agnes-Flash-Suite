# -*- coding: utf-8 -*-
"""
Agnes 视频任务收取节点（异步两段式·收取段，单任务）
=====================================================
输入 1 路 task_url（直连 Agnes 视频任务提交 的 task_url 输出；完整轮询 URL
自带域名，跨域名提交的任务同样可查）+ api_key（可直连 提交 节点的 api_key
穿透输出，免再配），节点内轮询查询任务状态：

  completed  → 自动下载 mp4 到 ComfyUI output/agnes_videos/，
               video 输出=环境动态类型（同 文生视频 三档）：
               原生 ComfyUI = VIDEO（VideoFromFile 惰性文件引用，
               可直连 Save Video：SaveVideo 重编码到 output/video/ 并预览）
               / VHS = VHS_VIDEOINFO / 无视频节点 = 路径字符串，
               status 输出=服务端视频 URL；
  failed     → status 输出=Agnes 服务端错误响应内容；
  task_url=0 → 上游 视频任务提交 失败标记（未生成任务）：跳过整个收取过程
               （零轮询零下载），status 输出 error 内容；
  processing → 到 timeout 仍生成中（不算任务失败）：
               status 输出=提示可再次右键运行本节点继续查（任务还在服务端）。

无文件态（failed/processing/empty/task_url=0/缺 Key）的 video 输出约定：
  原生 VIDEO 环境 → 生成 NO_VIDEO_ 前缀的 2 秒黑帧 720P 占位 mp4（PyAV，
  约 12KB、编码 0.3 秒）作为 VideoFromFile 引用输出：video 槽必须交接真实
  文件（空引用会崩 SaveVideo），但 status 携带完整 error 内容、队列不被
  打断、占位文件靠文件名自证；PyAV 不可用时回退旧红错约定；
  VHS/STRING 环境 → 返回空值不崩（行为不变）。

轮询节奏与 文生视频 一致：首查前等 60s（任务排队期），之后每 5s 一次；
下载自动 3 次重试（2/5/10 秒），URL 仍在有效期内可手动抢救。
"""

import os
from typing import Tuple

from ..api import AgnesClient, get_api_key
from ._output_docs import OutputDocsMixin
from .text2video import _VIDEO_MODE, _VIDEO_OUTPUT_TYPE, _make_result

# 输出目录：与 文生视频 节点一致（ComfyUI output/agnes_videos/）
_COMFYUI_OUTPUT_DIR = None

# VHS 档无文件态的空视频引用（同 文生视频 _error 的 vhs 分支）
_VHS_EMPTY = {"filename": "", "subfolder": "", "type": "output"}


def _make_placeholder_video(state: str, out_dir: str) -> str:
    """生成 2 秒黑帧 720P 占位 mp4（NO_VIDEO_ 前缀），返回本地路径。

    原生 VIDEO 环境无真实视频文件时填充 video 槽用（空引用会令下游
    SaveVideo 崩溃）；文件名 NO_VIDEO_{state}_{秒级时间戳}.mp4 自证身份。
    并发同名同状态文件内容完全一致，互相覆盖无害。PyAV 不可用抛错。
    """
    import time as _time
    try:
        import av
    except ImportError as e:
        raise RuntimeError(f"PyAV 不可用（{e}）")
    path = os.path.join(out_dir, f"NO_VIDEO_{state}_{int(_time.time())}.mp4")
    os.makedirs(out_dir, exist_ok=True)
    container = av.open(path, mode="w")
    try:
        stream = container.add_stream("libx264", rate=24)
        stream.width, stream.height, stream.pix_fmt = 1280, 720, "yuv420p"
        stream.options = {"preset": "ultrafast"}
        for i in range(48):  # 2 秒 @ 24fps
            frame = av.VideoFrame(720, 1280, "yuv420p")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))  # 清零=黑帧
            frame.pts = i
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    finally:
        container.close()
    return path


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
    """Agnes 视频任务收取：单路 task_url 轮询查询（URL 自带域名），completed 自动下载，输出 video（环境动态类型，可接 Save Video）+ status。"""

    DESCRIPTION = "视频任务异步收取（两段式第二段，单任务）：输入 1 路 task_url（直连 视频任务提交 的 task_url 输出；完整轮询 URL 自带域名，跨域名提交的任务同样可查）+ api_key（可直连 提交 的 api_key 穿透输出，免再配）；节点内轮询查询（首查前 60s、之后每 5s，timeout 默认 10 分钟），completed 自动下载 mp4 到 output/agnes_videos/（3 次重试）；输出 2 路：video（环境动态类型同 文生视频：原生 VIDEO 成功=真实 VideoFromFile 可直连 Save Video 出片预览、无文件态=NO_VIDEO_ 前缀黑帧占位 + status 携带 error 内容（队列不打断）/ VHS_VIDEOINFO / 路径字符串）+ status（completed=服务端视频 URL；failed=服务端错误内容；processing=到 timeout 未完成，再运行本节点继续查；empty=未连接 task_url）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING",)
    RETURN_NAMES = ("video", "status",)
    RETURN_LABELS = ("视频", "状态")
    OUTPUT_DOCS = {
        "video": "MP4 文件输出，类型随环境（同 文生视频 三档）：原生 ComfyUI=VIDEO（VideoFromFile 惰性文件引用，直连 Save Video：重编码到 output/video/ 并在输出预览面板播放）/ VHS=VHS_VIDEOINFO（可接 VHS 播放器）/ 无视频节点=本地路径字符串（ComfyUI output/agnes_videos/）；任务未完成/失败/未连接输入/0 标记/缺 Key 时：原生环境输出 NO_VIDEO_ 前缀黑帧占位 mp4（status 携带 error 内容，队列不打断；PyAV 不可用时回退红错），VHS/STRING 环境返回空值",
        "status": "任务状态：completed=服务端视频 URL（有效期内可浏览器直接播放/下载）；failed=Agnes 服务端错误响应内容（含任务级 failed 与下载失败诊断）；processing=到轮询超时任务未完成（可再次右键运行本节点继续查询）；error=收到 0 标记（上游 提交 失败，跳过收取，原因见 提交 节点 status）；empty=未连接 task_url",
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
                    "tooltip": "完整轮询 URL：直连 Agnes 视频任务提交 的 task_url 输出（含域名，跨域名提交的任务也能查）；留空=无任务可查（原生视频环境本节点红错提示，VHS/STRING 环境输出 empty）；收到 0=上游提交失败标记：跳过收取、出黑帧占位、status 输出 error 内容",
                }),
                "api_key": ("STRING", {
                    "label": "API Key",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key：轮询查询需 Bearer 鉴权，可直连 Agnes 视频任务提交 的 api_key 穿透输出（提交端实际用的 Key，免再配）；留空则跟随全局配置（API Key 配置节点/环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）；域名已在 task_url 里，无需再填请求地址",
                }),
                "timeout": ("INT", {
                    "label": "轮询超时",
                    "default": 600,
                    "min": 60,
                    "max": 7200,
                    "step": 60,
                    "tooltip": "本节点最长等待（秒，默认 600=10 分钟）：到点仍生成中=processing（不算失败），再次右键运行本节点即继续查（任务还在服务端）；视频一般 3-10 分钟出片，默认 10 分钟通常一趟收完，慢了就再点一次",
                }),
            },
        }

    def _no_video(self, state: str, detail: str) -> Tuple:
        """无文件态（failed/processing/empty/0 标记/缺 Key）的 video 侧输出。

        原生 VIDEO 环境：video 槽必须交接真实文件（空引用会令下游 SaveVideo
        在 get_dimensions 打不开空路径时崩溃），故生成 NO_VIDEO_ 前缀黑帧占位
        mp4 输出——status 携带完整 error 内容、队列不被打断；PyAV 不可用时
        回退旧约定（抛红色错误，文案指明下一步）；VHS/STRING 环境返回空值不崩。
        """
        status = f"{state}: {detail}"
        if _VIDEO_MODE == "comfy_api":
            try:
                placeholder = _make_placeholder_video(state, _get_output_dir())
            except Exception as e:
                print(f"[Agnes 视频任务收取] [错误] {status}（占位不可用：{e}；回退红错）")
                raise RuntimeError(f"[Agnes 视频任务收取] {status}")
            video_out = _make_result(placeholder, "720P")[0]
            print(f"[Agnes 视频任务收取] [错误] {status} → 出黑帧占位 {placeholder}")
            return (video_out, status)
        if _VIDEO_MODE == "vhs":
            return (_VHS_EMPTY, status)
        return ("", status)

    def generate(
        self,
        task_url: str = "",
        api_key: str = "",
        timeout: int = 600,
    ) -> Tuple:
        url = str(task_url or "").strip()
        if not url:
            return self._no_video("empty", "未连接 task_url 输入（可直连 Agnes 视频任务提交 的 task_url 输出）")
        if url == "0":
            # 上游 提交 节点失败标记（task_url=0=未生成任务）：跳过整个收取过程（零轮询零下载），
            # status 直接输出 error 内容；原生视频环境 video 槽不能给空引用（SaveVideo 会崩），
            # 故红错文案指明根因去向，VHS/STRING 环境返回空值 + error 状态（不崩）
            return self._no_video("error", "上游 Agnes 视频任务提交 未成功（task_url=0 标记）：原因见该节点 status 输出（如 503 队列满→等 5-10 分钟重跑 提交 节点）；提交成功后再次右键运行本节点收片")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return self._no_video("failed", "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）")

        client = AgnesClient(api_key)
        result = client.collect_video_task(url, timeout=timeout, output_dir=_get_output_dir())
        state = result["status"]
        if state == "completed":
            # 完成态：video 输出=环境动态类型（原生=VideoFromFile 惰性引用，SaveVideo 读盘重编码；零解码零内存开销）
            video_out = _make_result(result["save_path"], "720P")[0]
            print(f"[Agnes 视频任务收取] 完成：{result['save_path']}（服务端 URL: {result['video_url'][:80]}…，video 输出可直连 Save Video）")
            return (video_out, f"completed: {result['video_url']}")
        if state == "failed":
            return self._no_video("failed", result["error"])
        print(f"[Agnes 视频任务收取] 生成中（{result['error'].split('，')[0]}），可再次运行本节点继续查询")
        return self._no_video("processing", f"{result['error'].split('，')[0]}，可再次运行本节点继续查询")


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskCollect": AgnesVideoTaskCollect}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskCollect": "📥 Agnes 视频任务收取"}
