# -*- coding: utf-8 -*-
"""
Agnes 视频任务批量收取节点（异步两段式·收取段，20 任务并发）
============================================================
「Agnes 视频任务批量收取」：把 ≤20 个视频任务交给一个节点（输入 N → 输出 N
对应：task_i ↔ video_i），线程池并发轮询收取，全部 settled 才返回——
单节点完成 N 次「轮询 + 下载」，免 N 个 收取 实例逐个右键。

20 个输入 task_1…task_20（每槽 1 个任务，一一对应 video_1…video_20 输出）：
  - Agnes 视频任务提交 的 task_url_key 单线双参 JSON（{"task_url","api_key"}，
    一行带齐 URL+Key）：N 个提交实例的 task_url_key 输出直连 N 个槽，
    0 个中间合并节点；各槽 Key 可以全不同——条目自带 Key 只作用于本任务
    （每任务线程各建一个 AgnesClient），互不干扰；
  - 也接受 纯轮询 URL 字符串（Key 走 api_key 兜底输入 → 全局配置）；
  - "0"=上游 提交 失败标记：该槽跳过收取（零轮询零下载），记 error 状态，
    video_i 出默认视频填充（NO_VIDEO_ 黑帧占位/空值）；
  - 未连接/空=跳过该槽，记 empty 状态（槽号保位）。

合并输入 all_task_url_keys（面板置顶，优先于 20 槽逐一连线）：
  20 元素保位 JSON 数组，直连「Agnes 视频多任务并发提交」的 all_task_url_keys
  输出（一行带齐 N 个任务句柄，0 中间节点）；非空时按条目序填充
  task_1..task_20 槽（条目 ≤20 超出截断；条目可为 task_url_key 单线双参 JSON /
  "0" / 空 / 纯轮询 URL；"0" 条目跳过收取记 error 并默认视频占位填充，
  空条目记 empty 保位），video_1..20 按序输出；空=走上方 20 槽逐一连线
  语义（旧工作流零影响）。

轮询节奏与单 收取 一致：首查前 60s、之后每 5s（timeout 默认 600s/任务）；
completed 自动下载（3 次重试）到 ComfyUI output/agnes_videos/。

输出 22 槽 = video_1..video_20 + status + all_video_paths：
  video_i: 环境动态类型（同 文生视频/单收取 三档）：
           原生 ComfyUI=VIDEO（VideoFromFile 惰性引用，可直连 Save Video）
           / VHS=VHS_VIDEOINFO / 无视频节点=路径字符串；
           completed=真实文件，failed/processing/empty/"0" 标记/缺 Key
           =NO_VIDEO_ 前缀黑帧占位（原生，文件名带槽号，队列不打断）
           或空值（VHS/STRING）；
  status:  整批执行状态 JSON（槽号 1 起保位）：
           {"success":[completed 槽],"failed":[服务端失败/下载失败/缺 Key/
            网络异常槽],"processing":[到 timeout 未完成槽],"empty":[空输入槽],
            "error":["0" 标记槽], "details":{槽:原因}}；
  all_video_paths: 20 元素 JSON 数组（与 video_i 槽下标一一对应）：
           completed=本地落盘路径（下载失败时=服务端 URL），其余=""。

60 镜线接法（零中间节点版）：
  视频提示词批量 ×3 分段 → 视频任务提交 ×60（分 3 波，每波 20 实例）
  → 每波 20 个提交实例的 task_url_key 输出 直连 1 个 批量收取 实例的
  task_1…task_20（各槽 Key 可全不同）
  → 3 个批量收取 ×3 = 60 路 video 直连 Save Video 全量落盘
  （总时长≈max(各视频渲染时长)，非逐任务右键的 sum；出片期间画布可跑别的）。

分波全量合并输入接法（20 镜/波，提交侧单节点版）：
   视频提示词批量（分段）→ Agnes 视频多任务并发提交（all_prompts 一根线，
   提示词串行 × 池顺序短路，20 镜/波）
   → all_task_url_keys 一根线直连 1 个 批量收取 实例的 all_task_url_keys
   合并输入（0 中间节点；"0" 条目跳过收取并默认视频占位填充）
   → 20 路 video 按序直连 Save Video。
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

from ..api import AgnesClient, get_api_key
from ._output_docs import OutputDocsMixin
from .text2video import _VIDEO_MODE, _VIDEO_OUTPUT_TYPE, _make_result
from .video_task_collect import _make_placeholder_video, _get_output_dir, _VHS_EMPTY

MAX_TASKS = 20


def _parse_entry(raw) -> Tuple[str, str, str]:
    """单输入解析（从上到下）：task_url_key JSON 对象（{"task_url","api_key"}，
    提交节点第 4 输出，一行带齐 URL+Key）/ 嵌套 JSON 字符串元素 / 纯轮询 URL /
    "0" 标记 / 空。返回 (task_url, api_key, 形态标签)。"""
    raw = str(raw or "").strip()
    if not raw:
        return ("", "", "空")
    if raw == "0":
        return ("0", "", "0标记")
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        obj = None
    if isinstance(obj, dict):
        return (str(obj.get("task_url", "") or "").strip(),
                str(obj.get("api_key", "") or "").strip(), "JSON对象")
    if isinstance(obj, str):
        inner = obj.strip()
        try:
            inner_obj = json.loads(inner)
            if isinstance(inner_obj, dict):
                return (str(inner_obj.get("task_url", "") or "").strip(),
                        str(inner_obj.get("api_key", "") or "").strip(), "JSON字符串")
        except (json.JSONDecodeError, TypeError):
            pass
        return (inner, "", "URL")
    # 非 JSON 纯文本：取首行作 URL（URL 单行，多行输入防御性截取）
    first = raw.splitlines()[0].strip()
    return (first, "", "URL")


def _parse_all_tasks(raw) -> Tuple[list, str]:
    """合并输入 all_task_url_keys 解析（优先于 20 槽逐一连线）：20 元素保位 JSON
    数组（直连「Agnes 视频多任务并发提交」的 all_task_url_keys 输出）：条目可为
    task_url_key 单线双参 JSON 对象（{"task_url","api_key"}）/ "0" 标记 / 空 /
    纯轮询 URL 字符串 / 嵌套 JSON 字符串。条目 i → task 槽 i（超 20 条截断，保位）。
    返回 (raws(20 槽位保位列表，每槽=可喂 _parse_entry 的原始形态), 来源标签)。"""
    raw = str(raw or "").strip()
    if raw == "0":  # 防御：整个合并输入=0 标记（上游全灭）→ 全槽 0
        return (["0"] * MAX_TASKS, "0 标记（上游全灭，全槽跳过收取）")
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ([raw], "纯文本（1 条）")
    if isinstance(obj, str):
        obj = [obj]
    if not isinstance(obj, list):
        return ([raw], "非数组 JSON（按整段 1 条）")
    raws = []
    for el in obj:
        if isinstance(el, dict):
            raws.append(json.dumps(el, ensure_ascii=False))
        elif el is None:
            raws.append("")
        else:
            raws.append(el)
    truncated = len(raws) > MAX_TASKS
    if truncated:
        raws = raws[:MAX_TASKS]
    raws = raws + [""] * (MAX_TASKS - len(raws))
    return (raws, f"JSON 数组（{len(obj)} 条" + ("，超出 20 已截断" if truncated else "") + "）")


def _no_video(state: str, detail: str, slot: int = 0) -> Tuple:
    """无文件态（failed/processing/empty/0 标记/缺 Key）的 video 侧输出。

    与 单收取 _no_video 同约定：原生 VIDEO 环境出 NO_VIDEO_ 前缀黑帧占位
    mp4（video 槽必须交接真实文件，空引用会崩 SaveVideo；status 携带
    error 内容、队列不打断；PyAV 不可用回退红错）；VHS/STRING 环境回空值。
    批量场景占位文件名带槽号（NO_VIDEO_{state}_{slot}_*.mp4），20 槽同
    状态可辨识到槽。
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
    """Agnes 视频任务批量收取：all_task_url_keys 合并输入（优先，直连 视频多任务并发提交）或 20 个 task_i 逐一连线（task_i ↔ video_i，task_url_key 单线双参或纯 URL），线程池并发收取 ≤20 任务，输出 20 路 video（环境动态类型）+ 整批状态 JSON + 全部视频路径 JSON。"""

    DESCRIPTION = "视频任务异步批量收取（两段式第二段，20 任务并发）：合并输入 all_task_url_keys（面板置顶，优先）直连 Agnes 视频多任务并发提交 的 all_task_url_keys 输出（20 元素保位 JSON 数组，一行带齐 N 个任务句柄；非空时按条目序填充 task_1..task_20 槽，video_1..20 按序输出；\"0\" 条目跳过收取记 error 并默认视频占位填充，空条目记 empty 保位；空=走 20 槽逐一连线旧语义）；20 个输入 task_1…task_20（task_i 对应 video_i 输出：Agnes 视频任务提交 的 task_url_key 单线双参 JSON {task_url,api_key}，N 个提交实例直连 N 槽 0 中间节点，各槽 Key 可全不同；也接受纯轮询 URL（Key 走 api_key 兜底→全局）；0 标记=跳过记 error（默认视频占位填充）、空=跳过记 empty（槽号保位））；线程池并发轮询（max_concurrency 默认 10，每任务 60s 首查后每 5s，timeout 默认 600s），completed 自动下载（3 次重试）到 output/agnes_videos/；输出 22 槽：video_1..video_20（环境动态类型，completed=真实文件可直连 Save Video，无文件态=NO_VIDEO_ 黑帧占位（文件名带槽号）/空值）+ status 整批状态 JSON（success/failed/processing/empty/error 槽号清单+details 原因）+ all_video_paths 20 元素路径 JSON（completed=本地落盘路径，其余空）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    RETURN_NAMES = tuple(f"video_{i}" for i in range(1, MAX_TASKS + 1)) + ("status", "all_video_paths")
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE,) * MAX_TASKS + ("STRING", "STRING")
    RETURN_LABELS = tuple(f"视频 {i}" for i in range(1, MAX_TASKS + 1)) + ("执行状态 JSON", "全部视频路径 JSON")
    OUTPUT_DOCS = {
        **{f"video_{i}": f"task {i} 输入的任务（与 task_{i} 槽一一对应）：completed=本地 mp4（环境动态类型，可接 Save Video）；failed/processing/空输入/0 标记/缺 Key=NO_VIDEO_ 黑帧占位（原生环境，文件名带槽号）或空值（VHS/STRING）"
           for i in range(1, MAX_TASKS + 1)},
        "status": "整批执行状态 JSON（槽号 1 起保位）：success/failed/processing/empty/error 五类槽号清单 + details 槽→原因映射；可直接连 Agnes 文本拆分（JSON 数组模式）拆成 5 条名单做对接分析",
        "all_video_paths": "20 元素 JSON 数组（与 video_i 槽下标一一对应）：completed=本地落盘路径（下载失败时=服务端 URL），其余槽=空串；JSON 一行带走 20 条路径清单，可手动拷片/投喂其他工具",
    }

    @classmethod
    def INPUT_TYPES(cls):
        task_slots = {}
        for i in range(1, MAX_TASKS + 1):
            task_slots[f"task_{i}"] = ("STRING", {
                "label": f"任务 {i}",
                "multiline": False,
                "default": "",
                "placeholder": '{' + '"task_url": "https://api.agnes-ai.cn/agnesapi?video_id=…", "api_key": "sk-…"' + '} 或 纯轮询 URL',
                "tooltip": f"任务 {i} 输入（对应 视频 {i} 输出）：Agnes 视频任务提交 的 task_url_key 单线双参 JSON（一行带齐 URL+Key；各槽 Key 可全不同，条目自带 Key 只作用于本任务）；也接受 纯轮询 URL 字符串（Key 走 api_key 兜底输入→全局配置）；0=上游提交失败标记：跳过记 error；空=跳过该槽记 empty（槽号保位）",
            })
        return {
            "required": {
                "all_task_url_keys": ("STRING", {
                    "label": "全部任务 URL+Key（JSON 合并输入）",
                    "multiline": True,
                    "default": "",
                    "placeholder": '[{"task_url": "https://…/agnesapi?video_id=…", "api_key": "sk-…"}, "0", ""]\n直连 Agnes 视频多任务并发提交 的 all_task_url_keys 输出（20 元素保位 JSON 数组）',
                    "tooltip": "合并输入（面板置顶，优先于 20 槽逐一连线）：直连 Agnes 视频多任务并发提交 的 all_task_url_keys 输出（20 元素保位 JSON 数组，一行带齐 N 个任务句柄；条目可为 task_url_key 单线双参 JSON / \"0\" / 空 / 纯轮询 URL）；非空时按条目序填充 task_1..task_20 槽（超 20 条截断，\"0\" 条目跳过收取记 error 并默认视频占位填充，空条目记 empty 保位），video_1..20 按序输出；空=走现有 20 槽逐一连线语义（旧工作流零影响）",
                }),
                **task_slots,
            },
            "optional": {
                "api_key": ("STRING", {
                    "label": "API Key（兜底）",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "条目未自带 api_key（纯 URL 输入）时的兜底 Key：可连某 提交 节点的 api_key 穿透输出；留空则跟随全局配置（API Key 配置节点/环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）。task_url_key 输入自带 Key 的优先用自带",
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

    def generate(self, all_task_url_keys="", task_1="", task_2="", task_3="", task_4="", task_5="", task_6="", task_7="", task_8="", task_9="", task_10="",
                 task_11="", task_12="", task_13="", task_14="", task_15="", task_16="", task_17="", task_18="", task_19="", task_20="",
                 api_key="", timeout=600, max_concurrency=10) -> Tuple:
        # 20 个 task 槽（task_1…task_20）按位取；各槽独立解析（task_url_key JSON / 纯 URL / 0 / 空）
        individual = [task_1, task_2, task_3, task_4, task_5, task_6, task_7, task_8, task_9, task_10,
                      task_11, task_12, task_13, task_14, task_15, task_16, task_17, task_18, task_19, task_20]
        raws = list(individual)
        # ── 合并输入优先：all_task_url_keys 非空 → 按条目序填充 20 槽（20 路逐一连线忽略）──
        merged = str(all_task_url_keys or "").strip()
        if merged:
            raws, msrc = _parse_all_tasks(merged)
            n_individual = sum(1 for r in individual if str(r or "").strip())
            extra = (f"；task_1..20 逐一连线 {n_individual} 槽与合并输入并存，按置顶优先语义合并输入生效、逐一连线忽略"
                     if n_individual else "")
            print(f"[Agnes 视频任务批量收取] 合并输入 all_task_url_keys 生效（{msrc}{extra}）：按条目序填充 20 槽")
        entries = [_parse_entry(r)[:2] for r in raws]   # [(task_url, api_key), ×20]
        fallback_key = str(api_key or "").strip() or str(get_api_key() or "").strip()
        max_conc = max(1, min(MAX_TASKS, int(max_concurrency or 10)))

        def _status_json(success, failed, processing, empty, error, details=None):
            data = {"success": success, "failed": failed, "processing": processing,
                    "empty": empty, "error": error}
            if details:
                data["details"] = details
            return json.dumps(data, ensure_ascii=False, indent=2)

        def _all_slots():
            return list(range(1, MAX_TASKS + 1))

        # ── 全空：整批跳过，零 API 调用 ──
        if not any(u for u, _k in entries):
            print("[Agnes 视频任务批量收取] [跳过] 全部 20 个 task 输入为空（合并输入与槽连线均为空）：请连接 Agnes 视频多任务并发提交 的 all_task_url_keys 输出（一根线），或 Agnes 视频任务提交 的 task_url_key 输出（task_i ↔ 视频 i），零 API 调用")
            videos = [self._video_for("empty", "未连接 task 输入（槽号保位）", i) for i in _all_slots()]
            return tuple(videos) + (_status_json([], [], [], _all_slots(), []),
                                    json.dumps([""] * MAX_TASKS, ensure_ascii=False))

        # ── 分类：0 标记/空条目/缺 Key 零请求短路；其余进线程池 ──
        details: dict = {}
        paths = {i: "" for i in _all_slots()}
        zero = []    # (slot, state, detail)  请求前短路
        to_run = []  # (slot, url, key)
        for slot, (url, key) in enumerate(entries, 1):
            if not url:
                zero.append((slot, "empty", "未连接 task 输入（槽号保位）"))
            elif url == "0":
                zero.append((slot, "error", "上游 提交 未成功（task_url=0 标记，含 视频多任务并发提交 的 task_url_key 数组条目）：原因见该提交节点 status/details（如 503 队列满→等 5-10 分钟重跑提交节点）；本槽跳过收取，默认视频占位填充"))
            else:
                k = key or fallback_key
                if not k:
                    zero.append((slot, "failed", "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"))
                else:
                    to_run.append((slot, url, k))


        print("\n[Agnes 视频任务批量收取] 任务 "
              f"{len(to_run)} 条（含 0 标记 "
              f"{sum(1 for _s, st, _d in zero if st == 'error')} 条），"
              f"空槽 {sum(1 for _s, st, _d in zero if st == 'empty')} 个，"
              f"并发 {max_conc}，每任务 timeout {timeout}s")

        videos = [None] * MAX_TASKS
        success, failed, processing, empty, error = [], [], [], [], []
        results = {}

        # ── 短路槽先落位（零请求）──
        for slot, state, detail in zero:
            if state == "empty":
                empty.append(slot)
            elif state == "error":
                error.append(slot)
            else:
                failed.append(slot)
            details[slot] = detail
            videos[slot - 1], _st = self._video_for(state, detail, slot)
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
                            paths[slot] = res.get("save_path") or res.get("video_url") or ""
                            print(f"[Agnes 视频任务批量收取] #{slot} 完成 {paths[slot]}（服务端: {str(res.get('video_url', ''))[:60]}…）")
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
                        videos[slot - 1], _st = self._video_for_file(
                            results[slot].get("save_path") or "", slot)
                    else:
                        videos[slot - 1], _st = self._video_for(slot_state, details.get(slot, ""), slot)

        # ── 槽位补全（防御：理论上 20 槽全部已落位）──
        for i in _all_slots():
            if videos[i - 1] is None:
                videos[i - 1], _ = _no_video("empty", "未处理槽（防御）", i)

        success.sort(); failed.sort(); processing.sort(); empty.sort(); error.sort()
        status_json = _status_json(success, failed, processing, empty, error,
                                   details=details or None)
        all_paths_json = json.dumps([paths[i] for i in _all_slots()], ensure_ascii=False)
        print(f"[Agnes 视频任务批量收取] 完成：成功 {len(success)}/20，失败 {len(failed)}，"
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
