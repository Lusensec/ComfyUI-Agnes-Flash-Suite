# -*- coding: utf-8 -*-
"""
Agnes 分镜提示词批量生成节点
============================
「Agnes 总导演 / Agnes 场景切分」合并槽 all_scenes（JSON 数组）驱动的
分镜提示词批量生成节点：1 路 all_scenes 全文合并输入（↔ 总导演/场景切分
all_scenes 输出，一根线直连；也接受单条分镜纯文本，视为 1 条），
线程池并发生成英文生图提示词（max_concurrency 限制同时请求数，默认 10，
超出排队执行），60 路 detailed_prompt + 1 路 status + 1 路 all_prompts 全提示词
JSON 输出 + 3 路分段 all_prompts_1_20 / _21_40 / _41_60（各段成功提示词 JSON 数组，
分段喂 Agnes 分镜图批量生成 出图）（整批执行状态 JSON：
{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析；
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）。

- 参数与单条「Agnes 分镜提示词生成」完全一致（style/base_url/api_key/model/
  reasoning_effort），整批共用，另加 资产提取 5 路 JSON 注入槽
  （characters/locations/costumes/props/weather，整批共用、非空才随每条发送）
  与 max_concurrency 速率限制
- all_scenes 解析（从上到下）：JSON 数组=逐条处理（跳过空项，超 60 条截断并
  日志标注）；JSON 字符串=1 条；非 JSON 纯文本（单条分镜直连/手动粘贴）=1 条；
  空输入=整批跳过（零 API 调用）
- 条目不足 60 时其余槽为空槽（status empty）；单条失败不影响其他条
- 每个工作线程内部各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型接法（分镜线）：
  Agnes 剧本生成/解说剧本生成（故事文本）
      ├─▶ Agnes 总导演（all_scenes 合并槽，JSON 数组）─▶ Agnes 分镜提示词批量生成（all_scenes）
      │      （+ Agnes 资产提取 角色/场景/服装/道具/天气 JSON 任选注入，整批共用）
      │      ─▶ all_prompts（全部提示词 JSON）─▶ ≤20 条直连 Agnes 分镜图批量生成 all_prompts 出关键帧 / 整批审改存档
      │      ─▶ all_prompts_1_20 / _21_40 / _41_60（分段 JSON）
      │         ─▶ Agnes 分镜图批量生成 实例①②③（all_prompts 一根线各连一段，分波出图控 RPM）
      │            ─▶ 各实例 all_images ─▶ Agnes 图像拼图（batch_images，每波一张 20 图分段总览）
       │      ─▶ detailed_prompt_1..60（单镜）─▶ Agnes 文生图（逐镜关键帧）→ 关键帧生视频
      └─▶ Agnes 资产提取 ─▶ 资产线（资产提示词批量/三视图批量 → 参考图回流分镜线保一致性）
  轻量替代：Agnes 场景切分（all_scenes 合并槽）直连本节点；
  单镜处理：总导演 分镜_i / 场景切分 场景_i 单路纯文本直连 all_scenes 输入（视为 1 条）
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import (
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
)
from .prompt_generator import AgnesScenePromptGenerator, STYLE_OPTIONS
from ._output_docs import OutputDocsMixin


MAX_SLOTS = 60


class AgnesScenePromptBatch(OutputDocsMixin):
    """分镜提示词批量生成：all_scenes 合并输入（JSON 数组/纯文本）并发生成英文提示词 + 1 路整批状态 JSON（线程池，速率可限）"""

    DESCRIPTION = "分镜提示词批量生成：all_scenes 合并输入（总导演/场景切分 all_scenes 输出，JSON 数组从上到下逐条处理，最多 60 条；单条分镜纯文本也接受）整批并发生成英文提示词（max_concurrency 限制同时请求数，默认 10），可整批注入 资产提取 5 路 JSON 保跨镜一致性，输出 60 路 detailed_prompt + 1 路 status 整批状态 JSON（success/error/empty 槽号清单）+ 1 路 all_prompts 全部提示词 JSON 数组 + 3 路分段 all_prompts_1_20/_21_40/_41_60（各段成功提示词 JSON，可分段直连 Agnes 分镜图批量生成 出关键帧），单条失败不影响其他条"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：detailed_prompt_1..60 + status + all_prompts + 3 路分段（共 65 槽）──
    RETURN_NAMES = tuple(f"detailed_prompt_{i}" for i in range(1, MAX_SLOTS + 1)) + (
        "status", "all_prompts", "all_prompts_1_20", "all_prompts_21_40", "all_prompts_41_60",
    )
    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 5)
    RETURN_LABELS = tuple(f"英文分镜提示词 {i}" for i in range(1, MAX_SLOTS + 1)) + (
        "执行状态 JSON", "全部提示词 JSON",
        "全部提示词 JSON（1-20）", "全部提示词 JSON（21-40）", "全部提示词 JSON（41-60）",
    )
    OUTPUT_DOCS = {
        **{f"detailed_prompt_{i}": (
            f"第 {i} 个分镜（all_scenes 第 {i} 条）的英文生图提示词（风格化 + 角色/场景一致性描述 + 光线/色彩/质量词，"
            f"可直接接 文生图/图生图 出关键帧；空槽（条目不足 60）=空字符串；单条异常=空字符串（原因见 status）"
        ) for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号，含空响应],\"empty\":[空输入跳过槽号]}；"
            "槽号=all_scenes 条目序号（1 起）；全部请求失败时额外含 \"reason\" 字段（各槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，"
            "或接 LLM 对话让模型解读哪些槽需要重试"
        ),
        "all_prompts": (
            "本批成功生成的英文生图提示词 JSON 数组（json.dumps ensure_ascii=False indent=2，按槽号升序；失败/空槽不含；"
            "全空/缺 Key/零成功=空字符串）；≤20 条时可直连 Agnes 分镜图批量生成 all_prompts 输入（一根线批量出关键帧），"
            ">20 条（60 镜全量）请连 3 路分段 ×3 实例分波出图；亦可连 LLM 对话整批审改 / 存档"
        ),
        "all_prompts_1_20": (
            "槽 1-20 段成功提示词 JSON 数组（段内按槽号升序，跳过失败/空槽；该段零成功=空字符串）；"
            "可直连 Agnes 分镜图批量生成 all_prompts 输入（第一波 ≤20 张关键帧）"
        ),
        "all_prompts_21_40": (
            "槽 21-40 段成功提示词 JSON 数组（段内按槽号升序，跳过失败/空槽；该段零成功=空字符串）；"
            "可直连 Agnes 分镜图批量生成 all_prompts 输入（第二波 ≤20 张关键帧）"
        ),
        "all_prompts_41_60": (
            "槽 41-60 段成功提示词 JSON 数组（段内按槽号升序，跳过失败/空槽；该段零成功=空字符串）；"
            "可直连 Agnes 分镜图批量生成 all_prompts 输入（第三波 ≤20 张关键帧）"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "all_scenes": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[\n  \"[SHOT 1] 角色: 苏尘 (男) 场景: 客栈大厅 ...\",\n  \"[SHOT 2] ...\"\n]\n可连 总导演/场景切分 all_scenes 输出（JSON 数组，从上到下逐条）；\n也接受单条分镜纯文本（连 分镜_i / 场景_i 或粘贴），视为 1 条",
                "tooltip": "全文合并输入：① JSON 数组（总导演/场景切分 all_scenes 输出直连，条目从上到下逐条生成，最多 60 条，超出截断并日志标注；空项跳过）② 单条分镜纯文本（连任一 分镜_i / 场景_i 输出或手动粘贴，视为 1 条）③ 空=整批跳过（零 API 调用）",
            }),
            "style": (list(STYLE_OPTIONS), {
                "default": "cinematic",
                "tooltip": "图像风格（整批共用）：cinematic=电影感 / anime=动漫 / realistic=写实 / watercolor=水彩 / oil_painting=油画",
            }),
            "characters_json": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[{\"name\":\"角色名\",\"gender\":\"男/女\",\"appearance\":\"外貌描述\"}]",
                "tooltip": "角色信息 JSON（可连 Agnes 资产提取 角色JSON，整批共用）；留空=不注入该资产块",
            }),
            "locations_json": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[{\"name\":\"场景名\",\"description\":\"环境描述\",\"era\":\"时代背景\"}]",
                "tooltip": "场景信息 JSON（可连 Agnes 资产提取 场景JSON，整批共用）；留空=不注入该资产块",
            }),
            "costumes_json": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[{\"character\":\"角色名\",\"description\":\"服装描述\"}]",
                "tooltip": "服装信息 JSON（可连 Agnes 资产提取 服装JSON，整批共用）；留空=不注入该资产块",
            }),
            "props_json": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[\"道具1\", \"道具2\"]",
                "tooltip": "道具列表 JSON（可连 Agnes 资产提取 道具JSON，整批共用）；留空=不注入该资产块",
            }),
            "weather_json": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[\"天气/氛围 1\", \"天气/氛围 2\"]",
                "tooltip": "天气/氛围 JSON（可连 Agnes 资产提取 天气JSON，整批共用）；留空=不注入该资产块",
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
        return {"required": required, "optional": {}}

    @staticmethod
    def _parse_all_scenes(raw):
        """all_scenes 输入三档解析（从上到下）：
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

    def generate(self, all_scenes="", style="cinematic",
                 characters_json="", locations_json="", costumes_json="", props_json="", weather_json="",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_concurrency=10):
        items, source, truncated = self._parse_all_scenes(all_scenes)
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
            print(f"[Agnes 分镜提示词批量] {msg}")
            return tuple(msg for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
                "", "", "", "",
            )

        # ── 空输入跳过：一发请求都不发 ──
        if not items:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 总导演 / Agnes 场景切分 的 all_scenes 输出（JSON 数组），或连单条 分镜_i / 场景_i，或粘贴 JSON 数组/分镜文本"
            print(f"[Agnes 分镜提示词批量] {skip_msg}")
            return ("",) * MAX_SLOTS + (_status_json([], [], list(range(1, MAX_SLOTS + 1))), "", "", "", "")

        # 条目占槽 1..N，其余槽为空槽
        tasks = list(enumerate(items, 1))
        empty = [i for i in range(1, MAX_SLOTS + 1) if i > len(items)]

        _injected = [name for name, val in (("角色", characters_json), ("场景", locations_json),
                                             ("服装", costumes_json), ("道具", props_json), ("天气", weather_json)) if (val or "").strip()]
        print(f"\n[Agnes 分镜提示词批量] 输入={source}，条目 {len(tasks)}"
              + (f"（超 {MAX_SLOTS} 条已截断）" if truncated else "")
              + f"，并发 {max_conc}")
        print(f"  模型: {model}, 风格: {style}, 资产注入: {'、'.join(_injected) if _injected else '无'}")

        # 复用单条节点的成熟逻辑（每线程内各建 AgnesClient，Session 非线程安全不复用）
        gen = AgnesScenePromptGenerator()

        def _worker(idx, text):
            return gen.generate_prompt(
                scene_text=text,
                base_url=base_url,
                api_key=api_key,
                style=style,
                model=model,
                characters_json=characters_json,
                locations_json=locations_json,
                costumes_json=costumes_json,
                props_json=props_json,
                weather_json=weather_json,
                reasoning_effort=reasoning_effort,
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
                    if p and not p.startswith("[错误"):
                        prompts[i - 1] = p
                        success.append(i)
                        ok += 1
                        print(f"[Agnes 分镜提示词批量] #{i} 成功 {len(p)} 字 | {p[:40].strip()}...")
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
                        print(f"[Agnes 分镜提示词批量] #{i} 失败: {reasons[i][:120]}")
                except Exception as e:
                    prompts[i - 1] = f"[Error] {e}"
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 分镜提示词批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 分镜提示词批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 分镜提示词批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))

        # 全提示词 JSON：success 槽（升序）的成功提示词，失败/空槽不含；零成功=空串；可直连 分镜图批量生成
        _ok_prompts = [prompts[i - 1] for i in success]
        all_prompts = json.dumps(_ok_prompts, ensure_ascii=False, indent=2) if _ok_prompts else ""
        print(f"[Agnes 分镜提示词批量] all_prompts: {len(_ok_prompts)} 条成功提示词 → JSON 输出（可连 Agnes 分镜图批量生成）")

        # 3 路分段 JSON：槽 1-20 / 21-40 / 41-60 各自的成功提示词（段内升序、跳失败/空槽）
        # 分段零成功=空串；供 分镜图批量生成 all_prompts 输入分波出图（每波 ≤20 张，控 RPM）
        _succ = set(success)

        def _slice_json(lo, hi):
            """该槽段内的成功提示词（升序）→ (JSON 或 空串, 条数)"""
            chunk = [prompts[i - 1] for i in range(lo, min(hi, MAX_SLOTS) + 1) if i in _succ]
            return (json.dumps(chunk, ensure_ascii=False, indent=2) if chunk else ""), len(chunk)

        (s_1_20, n1), (s_21_40, n2), (s_41_60, n3) = _slice_json(1, 20), _slice_json(21, 40), _slice_json(41, 60)
        print(f"[Agnes 分镜提示词批量] 分段: 1-20 段 {n1} 条 / 21-40 段 {n2} 条 / 41-60 段 {n3} 条"
              f"（可分波连 Agnes 分镜图批量生成 all_prompts 出图）")

        return tuple(prompts) + (
            _status_json(success, error, empty, reason),
            all_prompts, s_1_20, s_21_40, s_41_60,
        )


NODE_CLASS_MAPPINGS = {"AgnesScenePromptBatch": AgnesScenePromptBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScenePromptBatch": "🎨 Agnes 分镜提示词批量生成"}
