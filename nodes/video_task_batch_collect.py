# -*- coding: utf-8 -*-
"""
Agnes 视频任务批量收取节点（异步两段式·收取段，20 槽并发）
==========================================================
与 Agnes 三视图批量生成 同范式：20 个可选 url_i 槽（各直连 视频任务提交 的
task_url 输出，不连线自动跳过不红框）或 1 路 all_urls JSON 数组合并输入，
节点内部线程池并发轮询（max_concurrency 限制并发数，默认 10，每线程独立
client——requests.Session 非线程安全），completed 槽自动下载 mp4。

输出（42 路）：
  video_1..20  各槽 MP4 本地路径（output/agnes_videos/；未完成/失败/空槽=空）
  status_1..20 各槽状态文本（completed=服务端视频 URL；failed=Agnes 服务端
               错误响应内容；processing=到 timeout 未完成可再次运行继续查；empty）
  batch_status 整批执行状态 JSON（completed/failed/processing/empty 槽号清单 +
               失败槽 reason 映射），可连 Agnes 文本拆分（JSON 数组模式）分析
  all_videos   成功槽按槽号升序的服务端视频 URL JSON 数组（零成功=空串）

槽位规则：url_1..20 与 all_urls 双通道并存时 url_i 优先；槽号=条目序号 1 起
（保位）；全部输入为空=整批跳过（零 API 调用）。
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import AgnesClient, get_api_key
from .video_task_collect import _get_output_dir
from ._output_docs import OutputDocsMixin

MAX_SLOTS = 20
MAX_CONCURRENCY_DEFAULT = 10


def _parse_all_urls(raw):
    """all_urls 输入三档解析（同 三视图批量 all_prompts 约定）：
    ① JSON 数组 → 逐条（空项保留占位——槽号保位）；② JSON 字符串/单 URL 纯文本 → 1 条；
    ③ 空 → 整批跳过。超出 MAX_SLOTS 截断。返回 (items, source, truncated)。"""
    raw = str(raw or "").strip()
    if not raw:
        return [], "空输入", False
    items, source = [], ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            source = "JSON 数组"
            items = [str(x).strip() for x in parsed]
        elif isinstance(parsed, str):
            source = "单 URL（JSON 字符串）"
            items = [parsed.strip()]
        else:
            source = "非数组 JSON（按整段 1 条）"
            items = [raw]
    except json.JSONDecodeError:
        source = "单 URL（纯文本）"
        items = [raw]
    truncated = len(items) > MAX_SLOTS
    if truncated:
        items = items[:MAX_SLOTS]
    return items, source, truncated


class AgnesVideoTaskBatchCollect(OutputDocsMixin):
    """视频任务批量收取：20 槽 task_url（可选，直连 视频任务提交 ×20）或 all_urls JSON 数组，线程池并发轮询+自动下载，输出 20 路 video + 20 路 status + 整批状态 JSON + all_videos URL 数组。"""

    DESCRIPTION = "视频任务批量收取（两段式第二段，20 槽并发）：20 个可选 url_i 槽（各直连 视频任务提交 的 task_url 输出）或 all_urls JSON 数组合并输入（url_i 优先），线程池并发轮询（max_concurrency 默认 10，每线程独立 client），completed 槽自动下载 mp4；输出 20 路 video（本地路径）+ 20 路 status（completed=服务端视频 URL/failed=服务端错误内容/processing=可再运行继续查/empty）+ 1 路 batch_status 整批状态 JSON（四桶槽号清单+失败 reason，可连 文本拆分 分析）+ 1 路 all_videos 成功槽视频 URL 升序 JSON 数组；全部输入为空=整批跳过零调用；单槽失败/未完成不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    RETURN_NAMES = (tuple(f"video_{i}" for i in range(1, MAX_SLOTS + 1))
                    + tuple(f"status_{i}" for i in range(1, MAX_SLOTS + 1))
                    + ("batch_status", "all_videos"))
    RETURN_TYPES = ("STRING",) * (2 * MAX_SLOTS + 2)
    RETURN_LABELS = (tuple(f"视频 {i}" for i in range(1, MAX_SLOTS + 1))
                     + tuple(f"状态 {i}" for i in range(1, MAX_SLOTS + 1))
                     + ("整批执行状态 JSON", "全部视频 URL JSON"))
    OUTPUT_DOCS = {
        **{f"video_{i}": f"第 {i} 个任务（槽 {i}）的 MP4 本地路径（ComfyUI output/agnes_videos/）；未完成/失败/空槽为空"
           for i in range(1, MAX_SLOTS + 1)},
        **{f"status_{i}": f"第 {i} 个任务状态：completed=服务端视频 URL；failed=Agnes 服务端错误响应内容；processing=到轮询超时未完成（可再次运行本节点继续查）；empty=该槽无输入"
           for i in range(1, MAX_SLOTS + 1)},
        "batch_status": (
            "整批执行状态 JSON：{\"completed\":[槽号],\"failed\":[槽号],\"processing\":[槽号],\"empty\":[槽号]}"
            "（槽号=任务序号 1 起保位）；存在失败槽时额外含 \"reason\" 字段（各失败槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 4 条名单（完成/失败/生成中/空输入）做对接分析"
        ),
        "all_videos": "成功槽按槽号升序的服务端视频 URL JSON 数组（零成功=空串；可在 URL 有效期内直接浏览器播放/下载，或作 LLM 对话素材清单）",
    }

    @classmethod
    def INPUT_TYPES(cls):
        slots = {
            f"url_{i}": ("STRING", {
                "label": f"轮询 URL {i}",
                "multiline": True,
                "default": "",
                "placeholder": "https://api.agnes-ai.cn/agnesapi?video_id=…&model_name=…",
                "tooltip": f"第 {i} 个任务的完整轮询 URL：直连 Agnes 视频任务提交 的 task_url 输出（可选，不连线自动跳过不红框；URL 自带域名，跨域名提交的任务也能查）",
            })
            for i in range(1, MAX_SLOTS + 1)
        }
        slots.update({
            "all_urls": ("STRING", {
                "label": "URL 合并输入",
                "multiline": True,
                "default": "",
                "placeholder": "['https://…/agnesapi?video_id=…&model_name=…', …]（JSON 数组 ≤20 条，超出截断）；单 URL 纯文本视为 1 条",
                "tooltip": "轮询 URL 合并输入：JSON 数组（≤20 条，超出截断并日志标注；空项=跳过该槽，槽号保位）或单 URL 纯文本（视为 1 条）；与 url_1..20 同时连接时 url_i 优先；全空=整批跳过（零 API 调用）",
            }),
            "api_key": ("STRING", {
                "label": "API Key",
                "default": "",
                "placeholder": "sk-...",
                "tooltip": "Agnes AI API Key：轮询查询需 Bearer 鉴权，留空自动加载全局（API Key 配置节点/环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）；域名已在各 task_url 里，无需再填请求地址",
            }),
            "max_concurrency": ("INT", {
                "label": "并发速率",
                "default": MAX_CONCURRENCY_DEFAULT,
                "min": 1,
                "max": MAX_SLOTS,
                "step": 1,
                "tooltip": f"并发速率限制：线程池大小（同时轮询数 1-{MAX_SLOTS}，默认 10）。非空槽数超过该值时排队执行；查询为轻量 GET，一般无需调小（频繁 429/503 再调小）",
            }),
            "timeout": ("INT", {
                "label": "轮询超时",
                "default": 1800,
                "min": 60,
                "max": 7200,
                "step": 60,
                "tooltip": "本节点最长等待（秒，默认 1800=30 分钟）：到点仍生成中的槽=processing（不算失败），再次右键运行本节点即继续查（任务还在服务端）；视频一般 3-10 分钟出片，默认 30 分钟通常一趟收完",
            }),
        })
        return {"required": slots, "optional": {}}

    def generate(
        self,
        url_1: str = "", url_2: str = "", url_3: str = "", url_4: str = "", url_5: str = "",
        url_6: str = "", url_7: str = "", url_8: str = "", url_9: str = "", url_10: str = "",
        url_11: str = "", url_12: str = "", url_13: str = "", url_14: str = "", url_15: str = "",
        url_16: str = "", url_17: str = "", url_18: str = "", url_19: str = "", url_20: str = "",
        all_urls: str = "",
        api_key: str = "",
        max_concurrency: int = MAX_CONCURRENCY_DEFAULT,
        timeout: int = 1800,
    ):
        url_slots = [
            str(url_1 or "").strip(), str(url_2 or "").strip(), str(url_3 or "").strip(),
            str(url_4 or "").strip(), str(url_5 or "").strip(), str(url_6 or "").strip(),
            str(url_7 or "").strip(), str(url_8 or "").strip(), str(url_9 or "").strip(),
            str(url_10 or "").strip(), str(url_11 or "").strip(), str(url_12 or "").strip(),
            str(url_13 or "").strip(), str(url_14 or "").strip(), str(url_15 or "").strip(),
            str(url_16 or "").strip(), str(url_17 or "").strip(), str(url_18 or "").strip(),
            str(url_19 or "").strip(), str(url_20 or "").strip(),
        ]
        all_urls_raw = str(all_urls or "").strip()
        api_key = str(api_key or "").strip()
        max_conc = max(1, min(MAX_SLOTS, int(max_concurrency or MAX_CONCURRENCY_DEFAULT)))
        timeout = int(timeout or 1800)

        # ── 槽位归一：url_i 优先；url_i 全空时回退 all_urls；槽号=条目序号 1 起保位 ──
        if any(url_slots):
            items, source, truncated = url_slots, "url_1..20 槽", False
        else:
            items, source, truncated = _parse_all_urls(all_urls_raw)
        items = (items + [""] * MAX_SLOTS)[:MAX_SLOTS]
        tasks = [(i, u) for i, u in enumerate(items, 1) if u]
        empty = [i for i, u in enumerate(items, 1) if not u]

        def _status_json(completed, failed, processing, empty_slots, reason=None):
            data = {"completed": completed, "failed": failed, "processing": processing,
                    "empty": empty_slots}
            if reason is not None:
                data["reason"] = reason
            return json.dumps(data, ensure_ascii=False, indent=2)

        videos = [""] * MAX_SLOTS
        statuses = [""] * MAX_SLOTS
        for i in empty:
            statuses[i - 1] = "empty"

        # ── 全空跳过：一发请求都不发 ──
        if not tasks:
            print("[Agnes 视频任务批量收取] [跳过] 全部输入为空：请连接 视频任务提交 的 task_url 输出（url_1..20）或粘贴 all_urls JSON 数组")
            return (tuple(videos) + tuple(statuses)
                    + (_status_json([], [], [], empty), ""))

        # ── Key 解析：缺 key 时非空槽全部记 failed（零 API 调用）──
        if not api_key:
            api_key = str(get_api_key() or "").strip()
        if not api_key:
            nokey = "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            failed_slots = [i for i in range(1, MAX_SLOTS + 1) if i not in set(empty)]
            for i in failed_slots:
                statuses[i - 1] = f"failed: {nokey}"
            print(f"[Agnes 视频任务批量收取] [错误] {nokey}（非空槽全部记 failed）")
            return (tuple(videos) + tuple(statuses)
                    + (_status_json([], failed_slots, [], empty, nokey), ""))

        print(f"\n[Agnes 视频任务批量收取] 输入={source}"
              + ("（超 20 条已截断）" if truncated else "")
              + f"，非空 {len(tasks)}/{MAX_SLOTS} 条，并发 {max_conc}，单任务超时 {timeout}s")

        # ── 每线程独立 client（Session 非线程安全）──
        def _worker(idx, url):
            client = AgnesClient(api_key)
            return idx, client.collect_video_task(url, timeout=timeout, output_dir=_get_output_dir())

        completed, failed, processing = [], [], []
        reasons = {}
        url_by_slot = {}  # 槽号 → 服务端视频 URL（成功槽回填，供 all_videos 输出）
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, u): i for i, u in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    _, result = fut.result()
                    state = result["status"]
                    if state == "completed":
                        videos[i - 1] = result["save_path"]
                        statuses[i - 1] = f"completed: {result['video_url']}"
                        url_by_slot[i] = result["video_url"]
                        completed.append(i)
                        print(f"[Agnes 视频任务批量收取] #{i} 完成 → {result['save_path']}")
                    elif state == "failed":
                        statuses[i - 1] = f"failed: {result['error']}"
                        failed.append(i)
                        reasons[i] = result["error"] or "unknown"
                        print(f"[Agnes 视频任务批量收取] #{i} 失败: {result['error'][:80]}")
                    else:
                        statuses[i - 1] = f"processing: {result['error']}"
                        processing.append(i)
                        print(f"[Agnes 视频任务批量收取] #{i} 未完成（{timeout}s），再次运行本节点继续查")
                except Exception as e:
                    statuses[i - 1] = f"failed: {str(e) or type(e).__name__}"
                    failed.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    print(f"[Agnes 视频任务批量收取] #{i} 异常: {e}")
        completed.sort(); failed.sort(); processing.sort()

        uniq = {reasons[i] for i in failed} if failed else set()
        reason = uniq.pop() if len(uniq) == 1 else (dict(sorted(reasons.items())) if len(uniq) > 1 else None)
        batch_json = _status_json(completed, failed, processing, empty, reason)

        # 成功槽按槽号升序的服务端视频 URL 数组
        all_videos = json.dumps([url_by_slot[i] for i in completed],
                                 ensure_ascii=False, indent=2) if completed else ""
        print(f"[Agnes 视频任务批量收取] 完成：completed={len(completed)} failed={len(failed)} "
              f"processing={len(processing)} empty={len(empty)}（并发 {max_conc}）")
        print(f"[Agnes 视频任务批量收取] 状态: {batch_json[:200]}")
        return (tuple(videos) + tuple(statuses) + (batch_json, all_videos))


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskBatchCollect": AgnesVideoTaskBatchCollect}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskBatchCollect": "📥 Agnes 视频任务批量收取"}
