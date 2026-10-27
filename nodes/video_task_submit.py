# -*- coding: utf-8 -*-
"""
Agnes 视频任务提交节点（异步两段式·提交段）
==========================================
输入与退避策略与 Agnes 文生视频 节点完全一致（10 个输入同序同默认，
提交遇 503 队列满/429 限流按「重试次数」动态退避 10/30/60/60/60 秒），
但只执行「提交」这一段：POST /v1/videos 拿到任务 ID 后秒级返回，
不轮询、不下载——画布立刻解放，可继续跑其他工作流。

三个输出（均 STRING）：
  task_url: 完整轮询 URL（含域名 /agnesapi?video_id=…&model_name=…；
            域名跟随本节点请求地址，跨域名提交也拼对）——
            直连「Agnes 视频任务收取」的 task_url 输入；
  status:   成功="submitted: video_id=…"；失败=服务端错误响应内容原文
            （如 HTTP 503 队列满 / 400 参数错误的 detail）；
  api_key:  API Key 穿透——提交时实际使用的 Key（节点输入非空=输入值，
            否则=全局回退值），直连「收取」的 api_key 输入，
            收取端免再配 Key（缺 Key 短路时为空）。

60 镜线新接法：视频提示词批量 ×3 分段 → 视频任务提交 ×3（3 实例各连一段，
几分钟内提交完 60 个任务）→ 出片期间画布空闲 → 视频任务收取 ×N 实例（一任务一实例）
（右键部分执行，自动下载；多任务可各放一个收取实例分波收片）→ 60 镜视频全量落盘。
"""

from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    VIDEO_MODEL,
)
from ._output_docs import OutputDocsMixin

# 与 文生视频 节点一致的选项（同源同默认）
ASPECT_RATIOS = [
    "1:1", "2:3", "3:4", "4:5", "9:16", "9:21", "3:2", "4:3", "5:4", "16:9", "21:9",
]
RESOLUTIONS = ["720P"]
SECONDS_MIN = 4
SECONDS_MAX = 12
SECONDS_DEFAULT = 5


class AgnesVideoTaskSubmit(OutputDocsMixin):
    """Agnes 视频任务提交：只提交不等待（输入/退避同 文生视频），秒级返回 task_url + status，画布立刻解放。"""

    DESCRIPTION = "视频任务异步提交（两段式第一段）：输入与退避同 Agnes 文生视频（10 个输入同序，503 队列满按「重试次数」退避 10/30/60 秒），只执行提交段——POST 拿到任务 ID 即返回，不轮询不下载；输出 3 路：task_url（完整轮询 URL 含域名，直连 收取 节点）+ status（成功=submitted: video_id=…，失败=服务端错误响应原文）+ api_key 穿透（提交时实际使用的 Key，直连 收取 的 api_key 输入，收取端免再配 Key），出片期间画布可继续跑其他工作流"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING", "STRING", "STRING",)
    RETURN_NAMES = ("task_url", "status", "api_key",)
    RETURN_LABELS = ("轮询 URL", "状态", "API Key（穿透）")
    OUTPUT_DOCS = {
        "task_url": "完整轮询 URL（含域名 /agnesapi?video_id=…&model_name=…，域名跟随本节点请求地址）：直连 Agnes 视频任务收取 的 task_url 输入；提交失败时为空",
        "status": "任务状态：成功=submitted: video_id=…；失败=服务端错误响应内容（HTTP 503 队列满/400 参数错误等的原文诊断）；提交失败时 task_url 为空",
        "api_key": "API Key 穿透：提交时实际使用的 Key（节点输入非空=输入值，否则=全局回退值）：直连 Agnes 视频任务收取 的 api_key 输入，收取端免再配 Key；缺 Key 短路时为空",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "label": "提示词",
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入视频描述（建议英文），可连 Agnes 视频提示词生成 的 video_prompt 输出",
                    "tooltip": "要生成视频的文本描述（建议英文提示词，可连 Agnes 视频提示词生成 的 video_prompt 输出）",
                }),
                "base_url": ("STRING", {
                    "label": "请求地址",
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整；task_url 输出按此域名拼装（跨域名提交也拼对）",
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
                    "tooltip": "视频生成模型：Agnes Video 2.5-flash（4-12 秒 / 720P）",
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
                    "tooltip": "保留项（与 文生视频 输入一致）：本节点只提交不轮询，此值不生效；轮询时限在 收取 节点的 timeout 参数设置",
                }),
                "retries": ("INT", {
                    "label": "重试次数",
                    "default": 5,
                    "min": 0,
                    "max": 30,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "提交任务遇 503 队列满/429 限流时的自动重试次数：0=只提交一次，默认 5。重试间隔 10/30/60 秒，第 4 次起每次 60 秒（默认 5 次累计 220 秒/约 3.7 分钟），与 文生视频 完全一致",
                }),
            },
        }

    def generate(
        self,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = VIDEO_MODEL,
        resolution: str = "720P",
        aspect_ratio: str = "16:9",
        seconds: int = SECONDS_DEFAULT,
        seed: int = 0,
        max_wait_seconds: int = 600,
        retries: int = 5,
    ) -> Tuple:
        if not prompt.strip():
            return ("", "failed: 提示词为空：请描述视频内容", "")

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("", "failed: 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）", "")

        client = AgnesClient(api_key, base_url=base_url.strip() or None)
        result = client.submit_video_task(
            prompt=prompt.strip(),
            model=model,
            seconds=seconds,
            aspect_ratio=aspect_ratio,
            seed=seed if seed > 0 else None,
            retries=retries,
        )
        if result["ok"]:
            print(f"[Agnes 视频任务提交] {result['status']}（不轮询不下载，task_url 直连 收取 节点；api_key 穿透输出可直连收取端免再配 Key）")
        else:
            print(f"[Agnes 视频任务提交] [错误] {result['status']}")
        # 第 3 输出 api_key 穿透：提交时实际使用的 Key（节点输入或全局回退），收取端直连免再配
        return (result["task_url"], result["status"], api_key)


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskSubmit": AgnesVideoTaskSubmit}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskSubmit": "🎞️ Agnes 视频任务提交"}
