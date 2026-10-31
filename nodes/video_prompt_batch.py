# -*- coding: utf-8 -*-
"""
Agnes 视频提示词批量生成节点
===========================
「Agnes 分镜提示词批量生成」分段输出 all_prompts_1_20/_21_40/_41_60（JSON 数组 ≤20 条）
驱动的英文视频提示词批量生成节点：1 路 all_prompts 一根线直连任一分段（3 实例分波控 RPM，
与 分镜图批量 的 3 实例节拍对称），线程池并发生成（max_concurrency 限制同时请求数，默认 10，
超出排队执行），输出 20 路 video_prompt + 1 路 status 整批状态 JSON + 1 路 all_video_prompts
全部提示词 JSON（{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）。

- 参数与单条「Agnes 视频提示词生成」完全一致（style/mode/duration/base_url/api_key/
  model/reasoning_effort），整批共用，另加 max_concurrency 速率限制
- all_prompts 解析（从上到下）：JSON 数组=逐条处理（跳过空项，超 20 条截断并日志标注）；
  JSON 字符串=1 条；非 JSON 纯文本（单条提示词直连/手动粘贴）=1 条；空输入=整批跳过（零 API 调用）
- 条目不足 20 时其余槽为空槽（status empty）；单条失败不影响其他条
- 每个工作线程内部各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型接法（视频线，与 分镜图批量 3 实例分波对称）：
  Agnes 分镜提示词批量生成
      ├─ all_prompts_1_20 ─▶ Agnes 视频提示词批量生成 实例①（all_prompts，波 1）
      ├─ all_prompts_21_40 ─▶ Agnes 视频提示词批量生成 实例②（all_prompts，波 2）
      └─ all_prompts_41_60 ─▶ Agnes 视频提示词批量生成 实例③（all_prompts，波 3）
  各实例 video_prompt_1..20 一对一连 Agnes 关键帧生视频 prompt 输入
      （image 输入连同波 分镜图批量 的 image_1..20，槽号=条目序号天然对齐）
  all_video_prompts（全部视频提示词 JSON）可连 LLM 对话整批审改 / 存档
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import (
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
)
from .video_prompt import AgnesVideoPromptGenerator, VIDEO_PROMPT_MODES
from .prompt_generator import STYLE_OPTIONS
from ._output_docs import OutputDocsMixin


MAX_SLOTS = 20


class AgnesVideoPromptBatch(OutputDocsMixin):
    """视频提示词批量生成：all_prompts 一根线（分镜提示词批量任一分段，JSON 数组 ≤20 条）并发生成英文视频提示词 + 1 路整批状态 JSON（线程池，速率可限）"""

    DESCRIPTION = "视频提示词批量生成：all_prompts 一根线输入（直连 Agnes 分镜提示词批量生成 任一分段 all_prompts_1_20/_21_40/_41_60，各段 JSON 数组 ≤20 条；3 实例分波控 RPM 出 60 镜全量视频提示词；单条英文提示词纯文本也接受）整批并发生成英文视频提示词（max_concurrency 限制同时请求数，默认 10），输出 20 路 video_prompt + 1 路 status 整批状态 JSON + 1 路 all_video_prompts 全部视频提示词 JSON 数组，单条失败不影响其他条"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：video_prompt_1..20 + status + all_video_prompts（共 22 槽）──
    RETURN_NAMES = tuple(f"video_prompt_{i}" for i in range(1, MAX_SLOTS + 1)) + (
        "status", "all_video_prompts",
    )
    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 2)
    RETURN_LABELS = tuple(f"英文视频提示词 {i}" for i in range(1, MAX_SLOTS + 1)) + (
        "执行状态 JSON", "全部视频提示词 JSON",
    )
    OUTPUT_DOCS = {
        **{f"video_prompt_{i}": (
            f"第 {i} 条（all_prompts 第 {i} 条）的英文视频提示词（运动+运镜+一致性+风格+质量词，"
            f"直连 Agnes 关键帧生视频/文生视频/参考视频生成 的 prompt 输入，槽号与同波 分镜图批量 image_{i} 对齐）；"
            f"空槽（条目不足 {MAX_SLOTS}）=空字符串；单条异常=[Error] 前缀（原因见 status）"
        ) for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号，含空响应],\"empty\":[空输入跳过槽号]}；"
            "槽号=all_prompts 条目序号（1 起）；全部请求失败时额外含 \"reason\" 字段（各槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析，"
            "或接 LLM 对话让模型解读哪些槽需要重试"
        ),
        "all_video_prompts": (
            "本批成功生成的英文视频提示词 JSON 数组（json.dumps ensure_ascii=False indent=2，按槽号升序；失败/空槽不含；"
            "全空/缺 Key/零成功=空字符串）；喂视频节点请用 20 路 video_prompt_N 一对一接法，"
            "all_video_prompts 可连 Agnes LLM 对话整批审改 / 存档（≤20 条亦可连 Agnes 文本拆分 JSON 数组模式拆条）"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "all_prompts": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[\n  \"a cinematic shot of ...\",\n  \"close-up of ...\"\n]\n可连 Agnes 分镜提示词批量生成 任一分段 all_prompts_1_20/_21_40/_41_60（各段 JSON 数组 ≤20 条）；\n也接受单条英文提示词纯文本（连任一 detailed_prompt_N 或粘贴），视为 1 条",
                "tooltip": "视频提示词一根线输入：① JSON 数组（分镜提示词批量 任一分段 all_prompts_1_20/_21_40/_41_60 直连，3 实例分波控 RPM；条目从上到下逐条生成，最多 20 条，超出截断并日志标注；空项跳过）② 单条英文提示词纯文本（连任一 detailed_prompt_N 或手动粘贴，视为 1 条）③ 空=整批跳过（零 API 调用）",
            }),
            "style": (list(STYLE_OPTIONS), {
                "default": "cinematic",
                "tooltip": "画面风格（整批共用）：cinematic=电影感 / anime=动漫 / realistic=写实 / watercolor=水彩 / oil_painting=油画",
            }),
            "mode": (list(VIDEO_PROMPT_MODES), {
                "default": "keyframe",
                "tooltip": "视频节点素材形态（决定提示词写法，整批共用）：keyframe=关键帧生视频（首帧已定，只描述帧后运动，默认）；text=文生视频（无参考，完整描述）；reference=参考视频生成（<Picture N>/<Audio N> 标记指代）",
            }),
            "duration": ("INT", {
                "default": 5,
                "min": 4,
                "max": 12,
                "step": 1,
                "tooltip": "视频时长（秒，整批共用）：动作量与运镜节奏按此时长设计；需与下游视频节点 4-12s 设置一致",
            }),
            "base_url": ("STRING", {
                "multiline": False,
                "default": "",
                "placeholder": "https://api.agnes-ai.cn/v1",
                "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
            }),
            "api_key": ("STRING", {
                "multiline": False,
                "default": "",
                "placeholder": "sk-xxxxxxxx",
                "tooltip": "Agnes AI API Key，留空=自动加载全局配置",
            }),
            "model": (AVAILABLE_CHAT_MODELS, {
                "default": CHAT_MODEL,
                "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）",
            }),
            "reasoning_effort": (list(REASONING_EFFORTS), {
                "default": "auto",
                "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none / low / medium / high / max；2.0 旧模型不生效",
            }),
            "max_concurrency": ("INT", {
                "default": 10,
                "min": 1,
                "max": MAX_SLOTS,
                "step": 1,
                "tooltip": f"并发速率限制：线程池大小（同时请求数 1-{MAX_SLOTS}，默认 10）。条目超过该值时排队执行；频繁 429/503 就调小",
            }),
        }
        return {
            "required": required,
            "optional": {
                "retries": ("INT", {
                    "label": "重试次数",
                    "default": 3,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "tooltip": "逐条生效的失败重试次数（0=不重试，单条请求一次即止）：429 限流/5xx 自动退避（3/6/12s…），默认 3；整批最坏总时长≈条数×(1+重试次数)×请求超时",
                }),
                "timeout": ("INT", {
                    "label": "请求超时（秒）",
                    "default": 300,
                    "min": 30,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "单条 API 调用等待上限（秒），默认 300：长思考/长上下文可拉高到 3600",
                }),
            },
        }

    @staticmethod
    def _parse_all_prompts(raw):
        """all_prompts 输入三档解析（从上到下）：
        ① JSON 数组 → 逐条（str 化、去空白、跳过空项）；
        ② JSON 字符串 → 1 条；
        ③ 非 JSON 纯文本 / 其他 JSON 类型 → 整段 1 条。
        返回 (items, source, truncated)；超出 MAX_SLOTS 截断。"""
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
        truncated = len(items) > MAX_SLOTS
        if truncated:
            items = items[:MAX_SLOTS]
        return items, source, truncated

    def generate(self, all_prompts="", style="cinematic", mode="keyframe", duration=5,
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_concurrency=10, retries=3, timeout=300):
        items, source, truncated = self._parse_all_prompts(all_prompts)
        max_conc = max(1, min(MAX_SLOTS, int(max_concurrency or 10)))

        # ── Key 解析 ──
        api_key = str(api_key or "").strip()
        if not api_key:
            api_key = str(get_api_key() or "").strip()
        def _status_json(success, error, empty, reason=None):
            data = {"success": success, "error": error, "empty": empty}
            # 全部请求失败（success 为空且 error 非空）→ 附失败原因：
            # 各槽同一原因=字符串；不同=槽号→原因 映射
            if reason is not None and not success and error:
                data["reason"] = reason
            return json.dumps(data, ensure_ascii=False, indent=2)

        if not api_key:
            reason = "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            msg = f"[错误] {reason}"
            print(f"[Agnes 视频提示词批量] {msg}")
            return tuple(msg for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
                "",
            )

        # ── 空输入跳过：一发请求都不发 ──
        if not items:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 分镜提示词批量生成 的分段输出 all_prompts_1_20/_21_40/_41_60（各段 JSON 数组 ≤20 条），或连全量 all_prompts（≤20 条），或粘贴 JSON 数组/单条提示词"
            print(f"[Agnes 视频提示词批量] {skip_msg}")
            return ("",) * MAX_SLOTS + (_status_json([], [], list(range(1, MAX_SLOTS + 1))), "")

        # 条目占槽 1..N，其余槽为空槽
        tasks = list(enumerate(items, 1))
        empty = [i for i in range(1, MAX_SLOTS + 1) if i > len(items)]

        print(f"\n[Agnes 视频提示词批量] 输入={source}，条目 {len(tasks)}"
              + (f"（超 {MAX_SLOTS} 条已截断——本节点每波出 {MAX_SLOTS} 条提示词，60 镜全量请连 3 路分段 ×3 实例）" if truncated else "")
              + f"，并发 {max_conc}")
        print(f"  模型: {model}, 风格: {style}, 模式: {mode}, 时长: {duration}s")

        # 复用单条节点的成熟逻辑（每线程内各建 AgnesClient，Session 非线程安全不复用）
        gen = AgnesVideoPromptGenerator()

        def _worker(idx, text):
            return gen.generate(
                shot_text=text,
                base_url=base_url,
                api_key=api_key,
                style=style,
                mode=mode,
                duration=duration,
                model=model,
                reasoning_effort=reasoning_effort,
                retries=retries,
                timeout=timeout,
            )

        prompts = [""] * MAX_SLOTS
        success, error = [], []
        reasons = {}

        ok = fail = 0
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, t): i for i, t in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    p, log = fut.result()
                    p = p or ""
                    if p and not p.startswith("[错误") and not p.startswith("[Error"):
                        prompts[i - 1] = p
                        success.append(i)
                        ok += 1
                        print(f"[Agnes 视频提示词批量] #{i} 成功 {len(p)} 字 | {p[:40].strip()}...")
                    else:
                        prompts[i - 1] = p
                        error.append(i)
                        if p:
                            slot_reason = p.split("]", 1)[1].strip() if "]" in p else p
                            reasons[i] = slot_reason or p
                        else:
                            # 单节点异常/空响应路径：content 为空，原因取日志首行
                            first = (log or "").strip().splitlines()
                            reasons[i] = first[0] if first else "生成失败（详见节点日志）"
                        fail += 1
                        print(f"[Agnes 视频提示词批量] #{i} 失败: {reasons[i][:120]}")
                except Exception as e:
                    prompts[i - 1] = f"[Error] {e}"
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 视频提示词批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 视频提示词批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 视频提示词批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))

        # 全部视频提示词 JSON：success 槽（升序）的成功提示词，失败/空槽不含；零成功=空串；喂视频节点用 20 路槽位一对一
        _ok_prompts = [prompts[i - 1] for i in success]
        all_video_prompts = json.dumps(_ok_prompts, ensure_ascii=False, indent=2) if _ok_prompts else ""
        print(f"[Agnes 视频提示词批量] all_video_prompts: {len(_ok_prompts)} 条成功提示词 → JSON 输出（可连 LLM 对话审改/存档）")

        return tuple(prompts) + (
            _status_json(success, error, empty, reason),
            all_video_prompts,
        )


NODE_CLASS_MAPPINGS = {"AgnesVideoPromptBatch": AgnesVideoPromptBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoPromptBatch": "🎞️ Agnes 视频提示词批量生成"}
