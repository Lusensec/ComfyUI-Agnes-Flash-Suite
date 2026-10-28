# -*- coding: utf-8 -*-
"""
Agnes 视频任务批量收取节点（异步两段式·收取段，≤20 任务并发）
==============================================================
「Agnes 视频任务批量收取」：把 N 个视频任务（1-20 条）交给一个节点，
线程池并发轮询收取，全部 settled（completed/failed/processing）才返回——
单节点完成 N 次「轮询 + 下载」，免 N 个 收取 实例逐个右键。

输入 1 路 tasks（STRING，JSON 合并输入，多形态宽容解析）：
  ① JSON 数组（主形态）：元素 = Agnes 视频任务提交 的 task_url_key 单线双参
     对象 {"task_url","api_key"}（N 个提交实例的 task_url_key 拼数组，
     一行带齐 URL+Key）；元素也接受 纯 task_url 字符串（Key 走 api_key
     兜底）与 嵌套 JSON 字符串元素；
  ② 单个 JSON 对象 {"task_url","api_key"}（= 1 任务）；
  ③ 换行分隔的 JSON 对象行（Agnes 字符串合并 换行拼接 N 路 task_url_key
     的输出形态，逐行识别）；
  ④ 换行分隔的纯 URL 行 / 单行纯文本（= 1 任务）；
  ⑤ 空输入=整批跳过（零 API 调用）。
  条目 ≤20，超出截断（status 附 note）；条目 "0"=上游 提交 失败标记：
  跳过收取（零轮询零下载），记 error 状态；空条目=跳过，记 empty（槽号保位）。

轮询节奏与单 收取 一致：首查前 60s、之后每 5s（timeout 默认 600s/任务）；
completed 自动下载（3 次重试）到 ComfyUI output/agnes_videos/；
每任务线程各建一个 AgnesClient（请求的 Key 用该条自带 api_key，缺省走
api_key 兜底→全局配置；Session 非线程安全，不复用）。

输出 22 槽 = video_1..video_20 + status + all_video_paths：
  video_i: 环境动态类型（同 文生视频/单收取 三档）：
           原生 ComfyUI=VIDEO（VideoFromFile 惰性引用，可直连 Save Video）
           / VHS=VHS_VIDEOINFO / 无视频节点=路径字符串；
           completed=真实文件，failed/processing/empty/0 标记/缺 Key
           =NO_VIDEO_ 前缀黑帧占位（原生，同 单收取 B1 约定，队列不打断）
           或空值（VHS/STRING）；
  status:  整批执行状态 JSON（槽号 1 起保位）：
           {"success":[completed 槽],"failed":[服务端失败/下载失败/缺 Key/
            网络异常槽],"processing":[到 timeout 未完成槽],"empty":[空条目槽],
            "error":["0" 标记槽], "details":{槽:原因}, 超 20 条附 "note"}；
  all_video_paths: 20 元素 JSON 数组（与 video_i 槽下标一一对应）：
           completed=本地落盘路径（下载失败时=服务端 URL），其余=""。

60 镜线接法（批量收取版，免逐任务右键）：
  视频提示词批量 ×3 分段 → 视频任务提交 ×3（3 实例各连一段，几分钟提完）
  → 各实例 task_url_key 输出拼 JSON 数组（每段 ≤20 条：手拼 / LLM 对话
  生成 / 多路经 Agnes 字符串合并 换行拼接——本节点逐行识别）
  → 视频任务批量收取 ×3（线程池并发收取，单节点收完一段 20 镜）
  → 20×3 路 video 直连 Save Video 全量落盘。
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from ..api import AgnesClient, get_api_key
from ._output_docs import OutputDocsMixin
from .text2video import _VIDEO_MODE, _VIDEO_OUTPUT_TYPE, _make_result
from .video_task_collect import _make_placeholder_video, _get_output_dir, _VHS_EMPTY

MAX_TASKS = 20


def _entry_from_obj(obj) -> Tuple[str, str]:
    """dict 元素 → (task_url, api_key)（缺字段=空串，走兜底）。"""
    url = str(obj.get("task_url", "") or "").strip()
    key = str(obj.get("api_key", "") or "").strip()
    return (url, key)


def _parse_tasks(raw) -> Tuple[List[Tuple[str, str]], str, bool]:
    """tasks 输入多形态解析（从上到下）：
    ① JSON 数组 → 逐条（dict=task_url_key 单线双参对象；str=嵌套 JSON 字符串
       再解一层/纯 URL；空项=保位占位——槽号=条目位置）；
    ② JSON 对象 → 1 条；③ JSON 字符串 → 1 条；
    ④ 非 JSON 纯文本：换行分隔逐行识别（每行 JSON 对象=task_url_key，
       否则按 URL 行处理；空行跳过）；单行=1 条；
    ⑤ 空输入 → 空批。
    返回 (entries, source, truncated, total)；entries=(task_url, api_key) 保位列表（截断后），
    total=截断前条目数。"""
    raw = str(raw or "").strip()
    if not raw:
        return [], "空输入", False, 0
    parsed_obj = None
    try:
        parsed_obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed_obj = None
    if isinstance(parsed_obj, list):
        source = "JSON 数组"
        entries = []
        for x in parsed_obj:
            if isinstance(x, dict):
                entries.append(_entry_from_obj(x))
            elif isinstance(x, str):
                x = x.strip()
                if not x:
                    entries.append(("", ""))
                    continue
                try:
                    inner = json.loads(x)
                    if isinstance(inner, dict):
                        entries.append(_entry_from_obj(inner))
                    else:
                        entries.append((x, ""))
                except json.JSONDecodeError:
                    entries.append((x, ""))
            else:
                entries.append(("", ""))
    elif isinstance(parsed_obj, dict):
        source = "JSON 对象"
        entries = [_entry_from_obj(parsed_obj)]
    elif isinstance(parsed_obj, str):
        source = "JSON 字符串"
        entries = [(parsed_obj.strip(), "")]
    else:
        # 非 JSON 纯文本（换行分隔 JSON 对象行 / URL 行 / 单行）
        lines = [l.strip() for l in raw.splitlines()]
        entries, json_lines = [], 0
        for l in lines:
            if not l:
                continue
            try:
                obj = json.loads(l)
                if isinstance(obj, dict):
                    entries.append(_entry_from_obj(obj))
                    json_lines += 1
                else:
                    entries.append((l, ""))
            except json.JSONDecodeError:
                entries.append((l, ""))
        if json_lines:
            source = "换行 JSON 对象（字符串合并形态）"
        else:
            source = "换行文本" if len(lines) > 1 else "单行文本"
    total = len(entries)
    truncated = total > MAX_TASKS
    if truncated:
        entries = entries[:MAX_TASKS]
    return entries, source, truncated, total


def _no_video(state: str, detail: str, slot: int = 0) -> Tuple:
    """无文件态（failed/processing/empty/0 标记/缺 Key）的 video 侧输出。

    与 单收取 _no_video 同约定：原生 VIDEO 环境出 NO_VIDEO_ 前缀黑帧占位
    mp4（video 槽必须交接真实文件，空引用会崩 SaveVideo；status 携带
    error 内容、队列不打断；PyAV 不可用回退红错）；VHS/STRING 环境回空值。
    批量场景占位文件名带槽号后缀，避免 20 槽同状态同名混淆。
    """
    status = f"{state}: {detail}"
    if _VIDEO_MODE == "comfy_api":
        try:
            out_dir = _get_output_dir()
            # 槽号入状态标签：每槽独立编码一个占位（NO_VIDEO_{state}_{slot}_{ts}.mp4），
            # 文件名可辨识到槽，且无「共享 base 再复制/删除」的并发竞态
            tag = state if not slot else f"{state}_{slot}"
            path = _make_placeholder_video(tag, out_dir)
            video_out = _make_result(path, "720P")[0]
            print(f"[Agnes 视频任务批量收取] [错误] #{slot} {status} → 出黑帧占位 {path}")
            return (video_out, status)
        except Exception as e:
            print(f"[Agnes 视频任务批量收取] [错误] {status}（占位不可用：{e}；回退红错）")
            raise RuntimeError(f"[Agnes 视频任务批量收取] {status}")
    if _VIDEO_MODE == "vhs":
        return (_VHS_EMPTY, status)
    return ("", status)


class AgnesVideoTaskCollectBatch(OutputDocsMixin):
    """Agnes 视频任务批量收取：tasks JSON 合并输入（task_url_key 单线双参对象），线程池并发轮询 ≤20 任务，输出 20 路 video（环境动态类型）+ 整批状态 JSON + 全部视频路径 JSON。"""

    DESCRIPTION = "视频任务异步批量收取（两段式第二段，≤20 任务并发）：输入 1 路 tasks JSON 合并输入（元素=视频任务提交 的 task_url_key 单线双参对象 {task_url,api_key}，一行带齐 URL+Key；也接受单个对象/换行 JSON 对象行（字符串合并形态）/纯 URL 行；条目 0 标记=跳过记 error、空条目=跳过记 empty、超 20 条截断）；线程池并发轮询（max_concurrency 默认 10，每任务 60s 首查后每 5s，timeout 默认 600s），completed 自动下载（3 次重试）到 output/agnes_videos/；输出 22 槽：video_1..video_20（环境动态类型同 文生视频，completed=真实文件可直连 Save Video，无文件态=NO_VIDEO_ 黑帧占位+队列不打断）+ status 整批状态 JSON（success/failed/processing/empty/error 槽号清单+details 原因）+ all_video_paths 20 元素路径 JSON（completed=本地落盘路径，其余空）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    RETURN_NAMES = tuple(f"video_{i}" for i in range(1, MAX_TASKS + 1)) + ("status", "all_video_paths")
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE,) * MAX_TASKS + ("STRING", "STRING")
    RETURN_LABELS = tuple(f"视频 {i}" for i in range(1, MAX_TASKS + 1)) + ("执行状态 JSON", "全部视频路径 JSON")
    OUTPUT_DOCS = {
        **{f"video_{i}": f"第 {i} 条任务（tasks 第 {i} 条）的视频：completed=本地 mp4（环境动态类型，可接 Save Video）；failed/processing/empty/0 标记/缺 Key=NO_VIDEO_ 黑帧占位（原生环境）或空值（VHS/STRING）"
           for i in range(1, MAX_TASKS + 1)},
        "status": "整批执行状态 JSON（槽号 1 起保位）：success/failed/processing/empty/error 五类槽号清单 + details 槽→原因映射；超 20 条截断附 note；可直接连 Agnes 文本拆分（JSON 数组模式）拆成 5 条名单做对接分析",
        "all_video_paths": "20 元素 JSON 数组（与 video_i 槽下标一一对应）：completed=本地落盘路径（下载失败时=服务端 URL），其余槽=空串；JSON 一行带走 20 条路径清单，可手动拷片/投喂其他工具",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "tasks": ("STRING", {
                    "label": "任务列表",
                    "multiline": True,
                    "default": "",
                    "placeholder": '[\n  {"task_url": "https://api.agnes-ai.cn/agnesapi?video_id=…", "api_key": "sk-…"},\n  {"task_url": "…", "api_key": "…"}\n]（每段 ≤20 条）',
                    "tooltip": "任务合并输入（多形态宽容解析）：① JSON 数组=视频任务提交 的 task_url_key 单线双参对象（{" + '"task_url","api_key"' + "}" + "，N 实例拼数组，一行带齐 URL+Key；元素也接受纯 task_url 字符串，Key 走 api_key 兜底）② 单个 JSON 对象=1 任务 ③ 换行分隔的 JSON 对象行（N 路 task_url_key 经 Agnes 字符串合并 换行拼接的输出形态，逐行识别）④ 换行/单行纯 URL ⑤ 空=整批跳过（零 API 调用）；条目 0 标记=上游提交失败（跳过记 error）；超 20 条截断（status 附 note）",
                }),
                "api_key": ("STRING", {
                    "label": "API Key（兜底）",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "条目未自带 api_key 时的兜底 Key：可直连某提交节点 的 api_key 穿透输出（单 Key 场景全体共用）；留空则跟随全局配置（API Key 配置节点/环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）。条目自带 Key 的优先用自带",
                }),
                "timeout": ("INT", {
                    "label": "轮询超时（每任务）",
                    "default": 600,
                    "min": 60,
                    "max": 7200,
                    "step": 60,
                    "tooltip": "单任务最长等待（秒，默认 600=10 分钟，与 单收取 一致）：到点仍生成中=processing（不算失败），再次右键运行本节点即继续查未完成任务（completed 任务重查秒回不重下）；全批 settled 才返回",
                }),
                "max_concurrency": ("INT", {
                    "label": "并发数",
                    "default": 10,
                    "min": 1,
                    "max": MAX_TASKS,
                    "step": 1,
                    "tooltip": "线程池并发（同时轮询任务数 1-20，默认 10）：非空条目超过该值时排队执行；轮询是轻 GET，10 并发压力很小；频繁 429 就调小",
                }),
            },
        }

    def generate(
        self,
        tasks: str = "",
        api_key: str = "",
        timeout: int = 600,
        max_concurrency: int = 10,
    ) -> Tuple:
        entries, source, truncated, total = _parse_tasks(tasks)
        fallback_key = str(api_key or "").strip() or str(get_api_key() or "").strip()
        max_conc = max(1, min(MAX_TASKS, int(max_concurrency or 10)))

        def _status_json(success, failed, processing, empty, error, details=None, note=None):
            data = {"success": success, "failed": failed, "processing": processing,
                    "empty": empty, "error": error}
            if details:
                data["details"] = details
            if note:
                data["note"] = note
            return json.dumps(data, ensure_ascii=False, indent=2)

        def _empty_slots():
            return [i for i in range(1, MAX_TASKS + 1)]

        # ── 空输入：整批跳过，零 API 调用 ──
        if not entries:
            print(f"[Agnes 视频任务批量收取] [跳过] 输入为空：请连接 视频任务提交 的 task_url_key 输出（拼 JSON 数组），或粘贴 JSON/换行 URL；零 API 调用")
            videos = [self._video_for("empty", "未连接/空输入", i) for i in _empty_slots()]
            return tuple(videos) + (_status_json([], [], [], _empty_slots(), []),
                                    json.dumps([""] * MAX_TASKS, ensure_ascii=False))

        # ── 分类：0 标记/空条目 零请求短路；其余进线程池 ──
        details: dict = {}
        paths = {i: "" for i in range(1, MAX_TASKS + 1)}
        zero = []   # (slot, state, detail)  请求前短路
        to_run = []  # (slot, url, key)
        for slot, (url, key) in enumerate(entries, 1):
            if not url:
                zero.append((slot, "empty", "空条目（无 task_url，槽号保位）"))
            elif url == "0":
                zero.append((slot, "error", "上游 Agnes 视频任务提交 未成功（task_url=0 标记）：原因见该提交节点 status（如 503 队列满→等 5-10 分钟重跑 提交 节点）"))
            else:
                k = key or fallback_key
                if not k:
                    zero.append((slot, "failed", "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"))
                else:
                    to_run.append((slot, url, k))

        print(f"\n[Agnes 视频任务批量收取] 输入={source}，条目 {len(entries)}"
              + ("（超 20 条已截断）" if truncated else "")
              + f"，可收取 {len(to_run)} 条，短路 {len(zero)} 条，并发 {max_conc}，每任务 timeout {timeout}s")

        videos = [None] * MAX_TASKS
        success, failed, processing, empty, error = [], [], [], [], []
        results = {}

        # ── 短路条目先落槽（零请求）──
        for slot, state, detail in zero:
            if state == "empty":
                empty.append(slot)
            elif state == "error":
                error.append(slot)
            else:
                failed.append(slot)
            details[slot] = detail
            videos[slot - 1], st = self._video_for(state, detail, slot)
            print(f"[Agnes 视频任务批量收取] #{slot} [{state}] {detail}（零请求）")

        # ── 线程池并发收取（每线程各建 client：Key 按条目走，Session 非线程安全）──
        out_dir = _get_output_dir()

        def _worker(slot, url, key):
            client = AgnesClient(key)
            res = client.collect_video_task(url, timeout=timeout, output_dir=out_dir)
            return slot, res

        if to_run:
            with ThreadPoolExecutor(max_workers=max_conc) as ex:
                futs = {ex.submit(_worker, s, u, k): s for s, u, k in to_run}
                for fut in as_completed(futs):
                    slot = futs[fut]
                    try:
                        _, res = fut.result()
                        results[slot] = res
                        state = res["status"]
                        if state == "completed":
                            success.append(slot)
                            path = res.get("save_path") or res.get("video_url") or ""
                            paths[slot] = path
                            print(f"[Agnes 视频任务批量收取] #{slot} 完成 {path}（服务端: {str(res.get('video_url', ''))[:60]}…）")
                        elif state == "failed":
                            failed.append(slot)
                            details[slot] = res.get("error") or "服务端错误"
                            print(f"[Agnes 视频任务批量收取] #{slot} 失败: {details[slot]}")
                        else:  # processing
                            processing.append(slot)
                            details[slot] = f"{str(res.get('error', '')).split('，')[0]}（到 {timeout}s 未完成，再运行本节点继续查）"
                            print(f"[Agnes 视频任务批量收取] #{slot} 生成中（{details[slot]}）")
                    except Exception as e:
                        failed.append(slot)
                        details[slot] = f"网络/下载异常：{e}"
                        print(f"[Agnes 视频任务批量收取] #{slot} 异常: {e}")
                    slot_state = "success" if slot in success else ("failed" if slot in failed else "processing")
                    if slot in success:
                        # completed：video=环境动态类型真实文件（可直连 Save Video）
                        res = results[slot]
                        videos[slot - 1], st = self._video_for_file(
                            res.get("save_path") or "", slot)
                    else:
                        videos[slot - 1], st = self._video_for(slot_state, details.get(slot, ""), slot)

        # ── 槽位补全（未处理槽不应存在，防御）──
        for i in _empty_slots():
            if videos[i - 1] is None:
                videos[i - 1], _ = _no_video("empty", "未处理槽（防御）", i)

        success.sort(); failed.sort(); processing.sort(); empty.sort(); error.sort()
        note = f"输入 {total} 条，超出 20 条已截断" if truncated else None
        status_json = _status_json(success, failed, processing, empty, error,
                                   details=details or None, note=note)
        all_paths_json = json.dumps([paths[i] for i in _empty_slots()], ensure_ascii=False)
        print(f"[Agnes 视频任务批量收取] 完成：成功 {len(success)}/{len(entries)}，失败 {len(failed)}，"
              f"未完成 {len(processing)}，短路 {len(zero)}（并发 {max_conc}）")
        print(f"[Agnes 视频任务批量收取] 状态: success={success} failed={failed} processing={processing} "
              f"empty={empty} error={error}")
        return tuple(videos) + (status_json, all_paths_json)

    # ── video 槽构造 ──
    def _video_for(self, state: str, detail: str, slot: int) -> Tuple:
        """无文件态（failed/processing/empty/error）的 video 槽：占位/空值（同 单收取 B1 约定）。"""
        return _no_video(state, detail, slot)

    def _video_for_file(self, save_path: str, slot: int) -> Tuple:
        """completed 的 video 槽：环境动态类型引用本地文件（原生=VideoFromFile 惰性引用）。"""
        if not save_path:
            return _no_video("failed", "completed 但无本地文件（下载失败）", slot)
        return (_make_result(save_path, "720P")[0], f"completed: #{slot}")


NODE_CLASS_MAPPINGS = {"AgnesVideoTaskCollectBatch": AgnesVideoTaskCollectBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoTaskCollectBatch": "📥 Agnes 视频任务批量收取"}
