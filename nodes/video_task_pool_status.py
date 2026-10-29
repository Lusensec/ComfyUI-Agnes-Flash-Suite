# -*- coding: utf-8 -*-
"""
Agnes 视频任务并发结果节点（池提交结果展示终端）
=============================================
纯展示终端（零 API 调用、无需 Key）：接「Agnes 视频任务并发提交」的
status + pool_report + task_url_key 三路输出，格式化为逐条目结果矩阵——
哪条胜出（掩码 Key + 请求地址 + 命中轮次）、哪些条目 dead（鉴权/参数错误）、
哪些仍在队列满（末次诊断）、task_url_key 是否可直连「Agnes 视频任务批量收取」。

接法：并发提交 的 status / pool_report / task_url_key 直连本节点三路输入，
result 输出接 文本输入（AgnesNovelTextSource）或直接右键运行查看节点值。
"""

import json
from typing import Tuple

from ..api import _mask_key
from ._output_docs import OutputDocsMixin


class AgnesVideoTaskPoolStatus(OutputDocsMixin):
    """Agnes 视频任务并发结果：纯展示终端——接 并发提交 的 status/pool_report/task_url_key 三路，格式化为逐条目结果矩阵（胜出行/死条行/队列满行）+ 批量收取直连提示。"""

    DESCRIPTION = "池并发提交结果展示终端（零 API 调用、无需 Key）：接「Agnes 视频任务并发提交」的 status（提交状态）+ pool_report（逐条目 JSON 矩阵）+ task_url_key（胜出单线双参）三路输入，格式化输出 result 一行行可读文本——【状态】提交成败与末次诊断 /【胜出】条目序号+请求地址+掩码 Key+task_url_key 可直连 批量收取 task_i 提示 /【逐条目矩阵】每条目 attempts 次数与 result（success@roundN / dead:HTTPxxx / 末次诊断 / 未请求短路跳过）；并发提交 未运行/未连线时输出空态提示（不报错）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result",)
    RETURN_LABELS = ("结果（展示）",)
    OUTPUT_DOCS = {
        "result": "格式化结果文本（多行）：【状态】+【胜出】（掩码 Key，task_url_key 直连 批量收取 提示；0 标记=跳过提示）+【逐条目矩阵】；纯展示，零 API 调用，Key 已掩码可安全显示",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "status": ("STRING", {
                    "label": "提交状态",
                    "multiline": True,
                    "default": "",
                    "placeholder": "submitted: video_id=…（池 #2 / https://…） 或 failed: …",
                    "tooltip": "直连「Agnes 视频任务并发提交」的 status 输出",
                }),
                "pool_report": ("STRING", {
                    "label": "池报告（JSON）",
                    "multiline": True,
                    "default": "",
                    "placeholder": '[{"i":1,"base_url":"…","key":"sk-…****…","attempts":1,"result":"…"}]',
                    "tooltip": "直连「Agnes 视频任务并发提交」的 pool_report 输出（逐条目 JSON 数组；零请求短路=空数组 []）",
                }),
                "task_url_key": ("STRING", {
                    "label": "Task URL+Key（JSON）",
                    "multiline": False,
                    "default": "",
                    "placeholder": '{"task_url": "https://…/agnesapi?video_id=…", "api_key": "sk-…"}',
                    "tooltip": "直连「Agnes 视频任务并发提交」的 task_url_key 输出（胜出条目 URL+Key；本节点只展示掩码 Key 与直连提示，不参与任何请求）",
                }),
            },
        }

    def generate(self, status: str = "", pool_report: str = "", task_url_key: str = "") -> Tuple:
        lines = [f"【状态】{str(status).strip() or '（无状态：并发提交 节点未运行或未连线）'}"]

        # ── 胜出/task_url_key 直连提示 ──
        tuku = str(task_url_key or "").strip()
        tuku_obj = None
        if tuku:
            try:
                tuku_obj = json.loads(tuku)
            except (json.JSONDecodeError, TypeError):
                tuku_obj = None
        if isinstance(tuku_obj, dict):
            tuku_url = str(tuku_obj.get("task_url", "") or "").strip()
            winner_key = str(tuku_obj.get("api_key", "") or "").strip()
            if tuku_url and tuku_url != "0":
                lines.append(f"【胜出】{_mask_key(winner_key)}（task_url_key 非 0 标记，"
                              f"可直连「Agnes 视频任务批量收取」的 task_i 槽，批量收取 节点零改动）")
            else:
                lines.append("【胜出】无（task_url_key=0 标记：未生成任务，"
                              "批量收取 见 0 跳过记 error；请 5-10 分钟后重跑 并发提交 节点）")
        elif tuku:
            lines.append(f"【胜出】task_url_key 解析失败: {tuku[:80]}")

        # ── 逐条目矩阵 ──
        rep_raw = str(pool_report or "").strip()
        rep = []
        if rep_raw and rep_raw != "[]" and rep_raw != "0":
            try:
                obj = json.loads(rep_raw)
                if isinstance(obj, list):
                    rep = [e for e in obj if isinstance(e, dict)]
            except (json.JSONDecodeError, TypeError):
                rep = []
        if rep:
            lines.append("【逐条目矩阵】")
            for e in rep:
                i = e.get("i", "?")
                base = e.get("base_url", "") or "(全局)"
                key = e.get("key", "")
                att = e.get("attempts", 0)
                r = str(e.get("result", ""))
                lines.append(f" #{i} {base} {key} → {r}（attempts={att}）")
        else:
            lines.append("【逐条目矩阵】（无报告：池为空 / 零请求短路 / 未连线）")

        return ("\n".join(lines),)


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskPoolStatus": AgnesVideoTaskPoolStatus}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskPoolStatus": "📊 Agnes 视频任务并发结果"}
