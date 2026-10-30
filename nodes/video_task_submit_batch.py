# -*- coding: utf-8 -*-
"""
Agnes 视频多任务并发提交节点（异步两段式·提交段·多任务串行 × 池短路）
================================================================
「Agnes 视频任务并发提交」的多任务版本：1 路 all_prompts 合并输入
（JSON 数组 ≤20 条，直连「Agnes 视频提示词批量」任一分段的 all_video_prompts 输出，
或全量）替代单提示词输入；节点内部**串行循环**每个提示词——一次只提交一个
（绝不同双提示词并发，队列压力 = 逐个「并发提交」实例节拍），每条提示词走
多端点 Key 池顺序短路提交（#1 成功即停零浪费；400/401/403/404 条目标 dead
后续轮跳过；整轮全灭固定 30 秒退避 ±15% 抖动、Retry-After 头优先，机制与
单提交/并发提交 retries 完全一致，复用现成 submit_video_task_pool 实现）。

- 单条失败隔离：该槽 "0" 标记 + 诊断，**继续下一条**，不整批中止
- 最坏总时长 = N 条 × (1+retries) × 30 秒（retries=120 默认 → 单条最坏 ≈60 分钟，
  全批 20 条最坏可达 ≈20 小时）；两段式设计：提交完画布即解放，收取走 批量收取
- 22 槽输出（顺序与「Agnes 视频提示词批量」video_prompt_1..20 + status +
  all_video_prompts 一一对齐：提示词槽 i ↔ 任务句柄槽 i）：
  task_url_key_1..task_url_key_20（成功=单线双参 JSON {task_url,api_key}；
  失败="0"；空提示词条目/缺条="" 空槽，槽号 1 起保位）
  + status 整批执行状态 JSON（success/failed/empty 槽号清单 + details 原因）
  + all_task_url_keys 20 元素保位 JSON 数组（与 20 路同序；零提示词=""；
    直连「Agnes 视频任务批量收取」的 all_task_url_keys 合并输入，0 标记槽
    收取端自动跳过并默认视频占位填充）

典型接法（视频线·分波全量异步，20 镜/波）：
  Agnes 分镜提示词批量（分段）→ Agnes 视频提示词批量（实例/段）
  → all_video_prompts 直连 Agnes 视频多任务并发提交（all_prompts，一波 20 镜）
  → all_task_url_keys 一根线直连 批量收取 all_task_url_keys 合并输入
    （或 20 路 task_url_key_i 直连 批量收取 task_i 逐一接法，等价）
  → 20 路 video 直连 Save Video
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

MAX_TASKS = 20


class AgnesVideoTaskSubmitBatch(OutputDocsMixin):
    """Agnes 视频多任务并发提交：all_prompts 合并输入（视频提示词批量 all_video_prompts），提示词串行循环 × 池 Key 顺序短路提交，输出 20 路 task_url_key + status + all_task_url_keys。"""

    DESCRIPTION = ("视频任务多端点池多任务并发提交（两段式·提交段，提示词串行 × 池短路）："
                   "all_prompts 一根线输入（直连「Agnes 视频提示词批量」任一分段 all_video_prompts，"
                   "JSON 数组 ≤20 条；单条纯文本也接受=1 任务），节点内挨个循环逐条提交——"
                   "一次只提交一个提示词（绝不同双提示词并发），每条走池序顺序短路"
                   "（#1 成功即停零浪费，retries 机制同 并发提交：固定 30 秒/轮 ±15% 抖动、"
                   "Retry-After 优先、上限 120 轮累计 60 分钟；400/401/403/404 条目标 dead 跳过）；"
                   "单条失败=该槽 0 标记，继续下一条不整批中止；最坏总时长=N×(1+retries)×30 秒。"
                   "输出 22 槽（顺序对齐 视频提示词批量）：task_url_key_1..20（成功=单线双参 JSON "
                   "{task_url,api_key}；失败=0 标记；空槽=空）+ status 整批执行状态 JSON"
                   "（success/failed/empty 槽号清单+details 原因）+ all_task_url_keys 20 元素保位 JSON 数组"
                   "（直连「Agnes 视频任务批量收取」的 all_task_url_keys 合并输入）")

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：task_url_key_1..20 + status + all_task_url_keys（共 22 槽，顺序对齐 视频提示词批量）──
    RETURN_NAMES = tuple(f"task_url_key_{i}" for i in range(1, MAX_TASKS + 1)) + (
        "status", "all_task_url_keys",
    )
    RETURN_TYPES = ("STRING",) * (MAX_TASKS + 2)
    RETURN_LABELS = tuple(f"任务 URL+Key {i}" for i in range(1, MAX_TASKS + 1)) + (
        "执行状态 JSON", "全部任务 URL+Key JSON",
    )
    OUTPUT_DOCS = {
        **{f"task_url_key_{i}": (
            f"第 {i} 条提示词（all_prompts 第 {i} 条，非空条目顺序编号）的任务句柄：成功=单线双参 JSON "
            f'{{"task_url": 完整轮询 URL, "api_key": 胜出条目 Key}}（与 并发提交 task_url_key 同格式，'
            f'可直连 Agnes 视频任务批量收取 task_{i} 槽或 单收取）；'
            f'失败="0" 标记（全轮全灭/池不可用，收取端见 0 自动跳过并默认视频占位，原因见 status details）；'
            f'空槽（条目不足 {MAX_TASKS}/该位空条目）=空字符串'
        ) for i in range(1, MAX_TASKS + 1)},
        "status": (
            "整批执行状态 JSON（槽号 1 起，非空条目顺序编号）：{success:[成功槽号], failed:[失败槽号], "
            "empty:[超条目数/未使用槽号], details:{槽号:失败原因}}；全部成功=failed/empty 空清单；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成名单做对接分析，或接 LLM 对话解读哪些槽需重跑"
        ),
        "all_task_url_keys": (
            "20 元素保位 JSON 数组（与 task_url_key_1..20 同序逐槽一致：成功条目=单线双参 JSON 对象、"
            "失败条目=字符串 \"0\"、空槽=空字符串；零提示词输入=空字符串整体）：一根线直连「Agnes 视频任务批量收取」"
            "的 all_task_url_keys 合并输入（按序填充 task_1..task_20 槽，video_1..20 按序输出；0 标记槽"
            "收取端自动跳过并默认视频占位填充），或接 LLM 对话整批台账/存档"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "all_prompts": ("STRING", {
                    "label": "全部视频提示词（JSON 合并输入）",
                    "multiline": True,
                    "default": "",
                    "placeholder": "[\n  \"a cinematic shot of ...\",\n  \"close-up of ...\"\n]\n直连 Agnes 视频提示词批量 任一分段 all_video_prompts（JSON 数组 ≤20 条）；\n也接受单条英文视频提示词纯文本（视为 1 任务）",
                    "tooltip": "视频提示词一根线输入：① JSON 数组（直连 Agnes 视频提示词批量 all_video_prompts，一波 20 条；条目从上到下挨个串行提交，最多 20 条，超出截断并日志标注；空项跳过）② 单条英文提示词纯文本（视为 1 任务）③ 空=整批跳过（零 API 调用）",
                }),
                "pool_json": ("STRING", {
                    "label": "API Key 池（JSON）",
                    "multiline": True,
                    "default": "",
                    "placeholder": _POOL_JSON_EXAMPLE,
                    "tooltip": "「Agnes API Key 池配置」的 pool_json 输出直连（多组 Base URL+Key 条目 JSON 数组）；也可直接粘贴池 JSON；0 标记=上游池无有效条目（全槽 0 标记零请求短路）；条目 base_url 可空=跟随全局",
                }),
                "model": ([VIDEO_MODEL], {
                    "label": "模型",
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型：Agnes Video 2.5-flash（4-12 秒 / 720P），整批共用",
                }),
                "resolution": (RESOLUTIONS, {
                    "label": "分辨率",
                    "default": "720P",
                    "tooltip": "输出分辨率：Agnes 视频接口固定 720P（参数保留供展示与选择，目前仅此一项）",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "label": "宽高比",
                    "default": "16:9",
                    "tooltip": "画面宽高比（宽:高）：16:9 横屏 / 9:16 竖屏；API 文档列 16:9/9:16（可选，缺省服务端自动处理），其他比例自动就近映射；整批共用",
                }),
                "seconds": ("INT", {
                    "label": "时长（秒）",
                    "default": SECONDS_DEFAULT,
                    "min": SECONDS_MIN,
                    "max": SECONDS_MAX,
                    "step": 1,
                    "tooltip": "视频时长（秒，4-12 直控）：与上游 视频提示词批量 的 duration 保持一致；整批共用",
                }),
                "seed": ("INT", {
                    "label": "随机种子",
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "随机种子（0=每条随机，固定值可复现结果；整批共用同一种子）",
                }),
                "retries": ("INT", {
                    "label": "重试次数（轮数-1）",
                    "default": 120,
                    "min": 0,
                    "max": 120,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "与 并发提交 节点 retries 同机制（作用于每条提示词）：一轮=按池序全条目试探一次，整轮全灭固定 30 秒/轮退避（±15% 抖动，Retry-After 头优先）；默认 120（单条 121 轮、最坏 3600 秒/60 分钟，队列满等绿窗自然排上队）；可下调 0=单条只提交一次不退避；整批最坏总时长=条数×单条最坏",
                }),
            },
        }

    # ── 提示词三档解析（与 Agnes 视频提示词批量 同款）──
    @staticmethod
    def _parse_all_prompts(raw):
        """all_prompts 输入三档解析（从上到下）：
        ① JSON 数组 → 逐条（str 化、去空白、跳过空项，超出 20 条截断）；
        ② JSON 字符串 → 1 条；
        ③ 非 JSON 纯文本 / 其他 JSON 类型 → 整段 1 条。
        返回 (items, source, truncated)。"""
        raw = str(raw or "").strip()
        if not raw:
            return [], "空输入", False
        items, source = [], ""
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                source = "JSON 数组"
                items = [str(x).strip() for x in parsed]
                items = [x for x in items if x]
            elif isinstance(parsed, str):
                source = "JSON 字符串"
                items = [parsed.strip()] if parsed.strip() else []
            else:
                source = "非数组 JSON（按整段 1 条）"
                items = [raw]
        except json.JSONDecodeError:
            source = "纯文本（1 条）"
            items = [raw]
        truncated = len(items) > MAX_TASKS
        if truncated:
            items = items[:MAX_TASKS]
        return items, source, truncated

    @staticmethod
    def _status_json(success, failed, empty, details=None):
        data = {"success": success, "failed": failed, "empty": empty}
        if details:
            data["details"] = details
        return json.dumps(data, ensure_ascii=False, indent=2)

    def generate(
        self,
        all_prompts: str = "",
        pool_json: str = "",
        model: str = VIDEO_MODEL,
        resolution: str = "720P",
        aspect_ratio: str = "16:9",
        seconds: int = SECONDS_DEFAULT,
        seed: int = 0,
        retries: int = 120,
    ) -> Tuple:
        # ── 提示词解析（三档，与 视频提示词批量 同款）──
        items, source, truncated = self._parse_all_prompts(all_prompts)

        # ── 全批跳过：无有效提示词 → 全槽空，零 API 调用 ──
        if not items:
            print("[Agnes 视频多任务并发提交] [跳过] all_prompts 为空：请连接 Agnes 视频提示词批量 "
                  "all_video_prompts（JSON 数组 ≤20 条）或粘贴单条/JSON 提示词，零 API 调用")
            slots = [""] * MAX_TASKS
            status = self._status_json([], [], list(range(1, MAX_TASKS + 1)))
            return tuple(slots) + (status, "")

        if truncated:
            print(f"[Agnes 视频多任务并发提交] {source} 超出 {MAX_TASKS} 条，已截断至前 {MAX_TASKS} 条")

        # ── 池解析（池配置/并发提交 共用解析器）──
        entries, pool_err = parse_pool_entries(pool_json)
        n_items = len(items)
        if pool_err:
            # 池不可用（0 标记/解析错误/空池）→ 全部提示词槽 0 标记，零请求短路
            slots = ["0"] * n_items + [""] * (MAX_TASKS - n_items)
            failed = list(range(1, n_items + 1))
            empty = list(range(n_items + 1, MAX_TASKS + 1))
            details = {i: f"池不可用：{pool_err}（零请求短路）" for i in failed}
            status = self._status_json([], failed, empty, details)
            print(f"[Agnes 视频多任务并发提交] [错误] {pool_err} → 全槽 0 标记零请求短路"
                  f"（{n_items} 条提示词未提交，稍后修好池再运行本节点）")
            all_keys = json.dumps(slots, ensure_ascii=False, indent=2)
            return tuple(slots) + (status, all_keys)

        # ── 串行循环：一次只提交一个提示词（内层池 Key 顺序短路，复用 并发提交 机制）──
        success, failed, empty = [], [], []
        details = {}
        slots = [""] * MAX_TASKS
        print(f"\n[Agnes 视频多任务并发提交] 开始：{source} {n_items} 条提示词 × 池 {len(entries)} 条目，"
              f"串行逐条提交（一次一条，绝不同双并发；最坏总时长≈{n_items}×({1 + retries} 轮×30s)）")
        for i, prompt in enumerate(items, 1):
            res = submit_video_task_pool(
                pool=entries,
                prompt=prompt,
                model=model,
                seconds=seconds,
                aspect_ratio=aspect_ratio,
                seed=seed if seed > 0 else None,
                retries=retries,
            )
            if res["ok"]:
                slots[i - 1] = json.dumps(
                    {"task_url": res["task_url"], "api_key": res["api_key"]},
                    ensure_ascii=False)
                success.append(i)
                print(f"[Agnes 视频多任务并发提交] #{i}/{n_items} {res['status']}"
                      f"（串行节拍：上一条完成才提交下一条）")
            else:
                slots[i - 1] = "0"
                failed.append(i)
                details[i] = res["status"]
                print(f"[Agnes 视频多任务并发提交] #{i}/{n_items} [失败] {res['status']}"
                      f" → 0 标记，继续下一条提示词")
        empty = list(range(n_items + 1, MAX_TASKS + 1))
        status = self._status_json(success, failed, empty, details)
        all_keys = json.dumps(slots, ensure_ascii=False, indent=2)
        print(f"[Agnes 视频多任务并发提交] 完成：成功 {len(success)}/{n_items}，失败 {len(failed)}，"
              f"空槽 {len(empty)}（20 槽保位）；all_task_url_keys 直连 批量收取 all_task_url_keys 合并输入")
        return tuple(slots) + (status, all_keys)


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskSubmitBatch": AgnesVideoTaskSubmitBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskSubmitBatch": "🎞️ Agnes 视频多任务并发提交"}
