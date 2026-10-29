# -*- coding: utf-8 -*-
"""
Agnes 视频任务并发提交节点（异步两段式·提交段·多端点 Key 池）
==========================================================
「Agnes 视频任务提交」的池版本：同一提示词在多组「Base URL + Key」端点间
按池序顺序试探（短路 B 语义）——#1 成功即停，后续条目零请求零浪费；
#1 队列满 503 时 #2 的绿窗可能正好接住任务。
输入用「Agnes API Key 池配置」输出的池 JSON 替代 单提交 的 base_url + api_key
两个 widget；重试机制与 单提交 retries 完全相同（固定 30 秒/轮退避 ±15% 抖动、
Retry-After 头优先、上限 120 轮累计 3600 秒/60 分钟，累计等待时长与池大小无关；
400/401/403/404 条目标 dead 后续轮跳过，全灭提前终止）。

典型场景：国内 + 国外 Agnes 平台不同账号（条目各自独立 Base URL + Key）——
一边视频队列满（503 video_queue_full），另一边有绿窗时任务直接落地。

五个输出（均 STRING，顺序=前端面板自上而下）：
  task_url / api_key / task_url_key / pool_report：
  task_url（成功=胜出条目完整轮询 URL，失败=0 标记）/ api_key（胜出条目 Key 穿透）/
  task_url_key={"task_url","api_key"}（单线双参 JSON，胜出条目 Key 随行，
      直连「Agnes 视频任务批量收取」的 task_i 槽——批量收取 节点零改动）/
  pool_report: 每条目 JSON 数组 [{i, base_url, key(掩码), attempts, result}]
      （result ∈ success@roundN / dead:HTTPxxx / 末次诊断 / 未请求(短路跳过)），
      直连「Agnes 视频任务并发结果」展示节点做逐条目矩阵；
  status: 放在最下（pool_report 之下）——成功=submitted: video_id=…（池 #i / base_url），
      失败=末次诊断+建议（5-10 分钟重跑/增配池条目/错峰）

池线接法（与 60 镜线同构）：
  Agnes API Key 池配置（pool_json）→ 视频任务并发提交 ×N（N=镜头数/池容量）
  → task_url_key 直连 批量收取 task_1…task_20（各槽 Key=各胜出条目 Key，互不干扰）
  → 20 路 video 直连 Save Video；status/pool_report → 视频任务并发结果（逐条目矩阵）。
"""

import json
from typing import Tuple

from ..api import (
    VIDEO_MODEL,
    submit_video_task_pool,
)
from ._output_docs import OutputDocsMixin
from .api_key_pool import _POOL_JSON_EXAMPLE, parse_pool_entries
from .video_task_submit import (
    ASPECT_RATIOS,
    RESOLUTIONS,
    SECONDS_DEFAULT,
    SECONDS_MAX,
    SECONDS_MIN,
)


class AgnesVideoTaskSubmitPool(OutputDocsMixin):
    """Agnes 视频任务并发提交：多端点 Key 池顺序短路提交（#1 成功即停、后续条目零请求），retries 机制同 单提交，胜出条目 Key 随 task_url_key 直连 批量收取。"""

    DESCRIPTION = "视频任务多端点池并发提交（两段式·提交段，顺序短路 B）：同一提示词在「Agnes API Key 池配置」输出的池 JSON（多组 Base URL+Key 条目，国内+国外不同账号等）中按池序顺序试探——#1 成功即停、后续条目零请求（零浪费）；#1 队列满时后续条目绿窗可接住；retries 机制同 单提交（固定 30 秒/轮 ±15% 抖动、Retry-After 优先、上限 120 轮累计 60 分钟，400/401/403/404 条目标 dead 跳过、全灭提前终止）；只提交不轮询，秒级返回。输出 5 路（面板自上而下）：task_url（成功=胜出条目完整轮询 URL 含其域名，失败=0 标记）+ api_key（胜出条目 Key 穿透）+ task_url_key（单线双参 JSON {task_url,api_key}，胜出 Key 随行，直连 批量收取 task_i 零改动）+ pool_report（逐条目 JSON 矩阵，直连 并发结果 展示节点）+ status（置于最下：成功=submitted: video_id=…（池 #i / base_url），失败=末次诊断+建议）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("task_url", "api_key", "task_url_key", "pool_report", "status")
    RETURN_LABELS = ("轮询 URL", "API Key（胜出穿透）", "Task URL+Key（JSON）", "池报告（JSON）", "状态")
    OUTPUT_DOCS = {
        "task_url": "成功=胜出条目的完整轮询 URL（含该条目域名 /agnesapi?video_id=…&model_name=…，跨域名拼对）：直连 Agnes 视频任务收取/批量收取；失败=0 标记（未生成任务，收取节点见 0 直接跳过、status 输出 error 内容）",
        "api_key": "API Key 穿透：胜出条目实际使用的 Key（失败=空串）：直连 Agnes 视频任务收取 的 api_key 输入，收取端免再配 Key",
        "task_url_key": "单线双参 JSON：{\"task_url\": 轮询 URL（失败=0 标记）, \"api_key\": 胜出条目 Key}（与 task_url/api_key 两路输出同源）：直连 Agnes 视频任务批量收取 的 task_i 槽（批量收取 节点零改动，各槽 Key 可全不同）",
        "pool_report": "逐条目 JSON 数组 [{i, base_url, key(掩码), attempts, result}]：result ∈ success@roundN（胜出处）/ dead:HTTPxxx（鉴权/参数错误，后续轮跳过）/ 末次诊断（存活末态）/ 未请求（短路跳过）——直连「Agnes 视频任务并发结果」展示节点做逐条目矩阵；零请求短路=空数组 []",
        "status": "任务状态（面板最下输出）：成功=submitted: video_id=…（池 #i / base_url）；失败=末次诊断原文（503 队列满/400 参数错误等）+ 退避轮数/累计等待 + 建议（5-10 分钟重跑/增配池条目/错峰）；401 等鉴权错误=池内全部条目 dead 提前终止诊断",
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
                    "tooltip": "要生成视频的文本描述（建议英文提示词，可连 Agnes 视频提示词生成 的 video_prompt 输出）；全池条目共用同一提示词",
                }),
                "pool_json": ("STRING", {
                    "label": "API Key 池（JSON）",
                    "multiline": True,
                    "default": "",
                    "placeholder": _POOL_JSON_EXAMPLE,
                    "tooltip": "「Agnes API Key 池配置」的 pool_json 输出直连（多组 Base URL+Key 条目 JSON 数组）；也可直接粘贴池 JSON；0 标记=上游池无有效条目（零请求短路）；条目 base_url 可空=跟随全局",
                }),
                "model": ([VIDEO_MODEL], {
                    "label": "模型",
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型：Agnes Video 2.5-flash（4-12 秒 / 720P），全池条目共用",
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
                    "tooltip": "随机种子（0=每次随机，固定值可复现结果；全池条目共用同一种子）",
                }),
                "retries": ("INT", {
                    "label": "重试次数（轮数-1）",
                    "default": 5,
                    "min": 0,
                    "max": 120,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "与 单提交 节点 retries 同机制：一轮=按池序全条目试探一次，整轮全灭固定 30 秒/轮退避（±15% 抖动，Retry-After 头优先）；默认 5（6 轮、累计 150 秒）；上限 120（121 轮、累计 3600 秒/60 分钟，累计等待与池大小无关）；400/401/403/404 条目标 dead 后续轮跳过、全灭提前终止",
                }),
            },
        }

    def generate(
        self,
        prompt: str = "",
        pool_json: str = "",
        model: str = VIDEO_MODEL,
        resolution: str = "720P",
        aspect_ratio: str = "16:9",
        seconds: int = SECONDS_DEFAULT,
        seed: int = 0,
        retries: int = 5,
    ) -> Tuple:
        zero_report = "[]"
        zero_tuk = json.dumps({"task_url": "0", "api_key": ""}, ensure_ascii=False)

        if not prompt.strip():
            return ("0", "", zero_tuk, zero_report, "failed: 提示词为空：请描述视频内容")

        entries, err = parse_pool_entries(pool_json)
        if err:
            print(f"[Agnes 视频任务并发提交] [错误] {err} → 零请求短路（0 标记）")
            return ("0", "", zero_tuk, zero_report, f"failed: {err}")

        res = submit_video_task_pool(
            pool=entries,
            prompt=prompt.strip(),
            model=model,
            seconds=seconds,
            aspect_ratio=aspect_ratio,
            seed=seed if seed > 0 else None,
            retries=retries,
        )
        if res["ok"]:
            print(f"[Agnes 视频任务并发提交] {res['status']}（后续条目未请求，零浪费；"
                  f"task_url 直连 收取/批量收取，api_key 穿透=胜出条目 Key）")
        else:
            print(f"[Agnes 视频任务并发提交] [错误] {res['status']}")
        # 第 1 输出 task_url：成功=胜出条目完整轮询 URL；失败=0 标记（收取节点见 0 直接跳过）
        task_url_out = res["task_url"] if res["ok"] else "0"
        # 第 3 输出 task_url_key：单线双参 JSON（胜出条目 URL+Key 一行带齐，批量收取零改动直连）
        task_url_key_out = json.dumps(
            {"task_url": task_url_out, "api_key": res["api_key"]}, ensure_ascii=False)
        # 第 4 输出 pool_report：逐条目 JSON 矩阵（直连 并发结果 展示节点）
        pool_report_out = json.dumps(res["pool_report"], ensure_ascii=False)
        # 输出顺序：task_url / api_key / task_url_key / pool_report / status（status 置最下）
        return (task_url_out, res["api_key"], task_url_key_out, pool_report_out, res["status"])


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskSubmitPool": AgnesVideoTaskSubmitPool}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskSubmitPool": "🎞️ Agnes 视频任务并发提交"}
