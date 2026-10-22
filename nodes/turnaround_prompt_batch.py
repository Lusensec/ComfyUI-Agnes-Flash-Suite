# -*- coding: utf-8 -*-
"""
Agnes 三视图提示词批量生成节点
==============================
资产提示词合并输入驱动的三视图提示词批量生成节点：1 路 all_prompts 全文合并输入
（↔ 资产提示词批量 all_prompts 输出 / 资产提示词生成 单路输出，一根线直连；
也接受单条资产提示词纯文本，视为 1 条），线程池并发生成三视图英文提示词
（max_concurrency 限制同时请求数，默认 10，超出排队执行），
20 路 three_view_prompt + 1 路 status + 1 路 all_turnaround_prompts 全部三视图
提示词 JSON 输出（整批执行状态 JSON：{"success": [成功槽号], "error": [失败槽号],
"empty": [空输入槽号]}，可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单
做对接分析；全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，
不同=槽号→原因映射）。

- 参数与单条「Agnes 三视图提示词生成」完全一致（subject_type/base_url/
  api_key/model/reasoning_effort），整批共用，另加 max_concurrency 速率限制
- all_prompts 解析（从上到下）：JSON 数组=逐条处理（最多 20 条，超出截断并
  日志标注；空项=跳过该槽，槽号保位）；JSON 字符串/单条纯文本=1 条；
  空输入=整批跳过（零 API 调用）
- 单槽失败不影响其他槽：该槽输出 [Error] 前缀文本
- 每个工作线程内部各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型接法（资产线，一根线到底）：
  Agnes 资产提取.角色JSON ─▶ Agnes 资产提示词批量生成（all_items）
      ─▶ all_prompts（全部提示词 JSON）─▶ Agnes 三视图提示词批量生成（all_prompts）
      ─▶ all_turnaround_prompts（全部三视图提示词 JSON）─▶ Agnes 三视图批量生成（all_prompts）
  轻量单槽：资产提示词批量 english_prompt_i 单条纯文本直连 all_prompts 输入（视为 1 条）
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import (
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
)
from .turnaround_prompt import AgnesTurnaroundPromptGenerator, SUBJECT_TYPES
from ._output_docs import OutputDocsMixin


MAX_SLOTS = 20


class AgnesTurnaroundPromptBatch(OutputDocsMixin):
    """三视图提示词批量生成：all_prompts 合并输入（JSON 数组/纯文本）并发生成三视图英文提示词 + 1 路整批状态 JSON + 1 路 all_turnaround_prompts 全三视图提示词 JSON（线程池，速率可限）"""

    DESCRIPTION = "三视图提示词批量生成：all_prompts 合并输入（资产提示词批量 all_prompts 输出，JSON 数组从上到下逐条处理；单条资产提示词纯文本也接受）整批并发生成三视图英文提示词（max_concurrency 限制同时请求数，默认 10），输出 20 路 three_view_prompt + 1 路 status 整批状态 JSON（success/error/empty 槽号清单）+ 1 路 all_turnaround_prompts 全部三视图提示词 JSON 数组（可直连 Agnes 三视图批量生成 all_prompts 输入），单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：three_view_prompt_1..20 + status + all_turnaround_prompts（共 22 槽）──
    RETURN_NAMES = tuple(f"three_view_prompt_{i}" for i in range(1, MAX_SLOTS + 1)) + ("status", "all_turnaround_prompts")
    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 2)
    RETURN_LABELS = tuple(f"三视图提示词 {i}" for i in range(1, MAX_SLOTS + 1)) + ("执行状态 JSON", "全部三视图提示词 JSON")
    OUTPUT_DOCS = {
        **{f"three_view_prompt_{i}": (
            f"第 {i} 条资产提示词的完整三视图英文提示词（主体全部细节 + 分栏布局（左 1/3 特写 + 右 2/3 三视图）"
            f"+ 虚幻引擎渲染/PBR/柔和漫射光 + 纯白背景干净极简无阴影 + 8K 质量尾词，"
            f"可直接接 三视图生成(subject_desc)；空输入=空字符串；失败=[Error] 前缀文本"
        ) for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号，含空响应],\"empty\":[空输入跳过槽号]}；"
            "槽号=all_prompts 条目序号（1 起，保位）；全部请求失败时额外含 \"reason\" 字段（各槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，"
            "或接 LLM 对话让模型解读哪些槽需要重试"
        ),
        "all_turnaround_prompts": (
            "本批成功生成的三视图英文提示词 JSON 数组（json.dumps ensure_ascii=False indent=2，按槽号升序；失败/空槽不含；"
            "全空/缺 Key/零成功=空字符串）；可直连 Agnes 三视图批量生成 all_prompts 输入（一根线批量出三视图参考图），"
            "或连 LLM 对话整批审改 / 存档"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "all_prompts": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": '[\n  "a cinematic full-body character design ...",\n  "a close-up of ..."\n]\n可连 Agnes 资产提示词批量生成 all_prompts 输出（JSON 数组，一根线直连）；\n也接受单条资产提示词纯文本（连 english_prompt_i 或粘贴），视为 1 条',
                "tooltip": "资产提示词合并输入：① JSON 数组（资产提示词批量 all_prompts 输出直连，条目从上到下逐条生成三视图提示词，最多 20 条，超出截断并日志标注；空项=跳过该槽，槽号保位）② 单条资产提示词纯文本（连 资产提示词批量 english_prompt_i 或手动粘贴，视为 1 条）③ 空=整批跳过（零 API 调用）",
            }),
        }
        required.update({
            "subject_type": (list(SUBJECT_TYPES), {
                "default": "角色",
                "tooltip": "主体类型（决定分栏布局指令，20 槽共用）：角色=面部特写+全身正/侧/背 / 物品道具=细节特写+三视图 / 服装=细节特写+正/侧/背定妆 / 场景=局部特写+正立面/侧立面/俯视 / 载具=局部特写+整车三视图 / 通用",
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
                "tooltip": f"并发速率限制：线程池大小（同时请求数 1-{MAX_SLOTS}，默认 10）。非空提示词超过该值时排队执行；频繁 429/503 就调小",
            }),
        })
        return {"required": required, "optional": {}}

    @staticmethod
    def _parse_all_prompts(raw):
        """all_prompts 输入三档解析（从上到下）：
        ① JSON 数组 → 逐条（str 化、去空白；空项保留占位——槽号=条目位置，
          与旧 20 槽「空槽跳过」行为一致）；
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
            elif isinstance(parsed, str):
                source = "JSON 字符串"
                items = [parsed.strip()]
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

    def generate(self, all_prompts="", subject_type="角色",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_concurrency=10):
        items, source, truncated = self._parse_all_prompts(all_prompts)
        p = items
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
            print(f"[Agnes 三视图提示词批量] {msg}")
            return tuple(msg for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
                "",
            )

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(p, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入全部为空：请连接 Agnes 资产提示词批量 的 all_prompts 输出（JSON 数组），或连单条 english_prompt_i，或粘贴 JSON 数组/资产提示词"
            print(f"[Agnes 三视图提示词批量] {skip_msg}")
            return ("",) * MAX_SLOTS + (_status_json([], [], list(range(1, MAX_SLOTS + 1))), "")

        print(f"\n[Agnes 三视图提示词批量] 输入={source}，条目 {len(p)}"
              + ("（超 20 条已截断）" if truncated else "")
              + f"，非空 {len(tasks)} 条，并发 {max_conc}")
        print(f"  模型: {model}, 主体类型: {subject_type}")

        # 复用单条节点的成熟逻辑（每线程内各建 AgnesClient，Session 非线程安全不复用）
        gen = AgnesTurnaroundPromptGenerator()

        def _worker(idx, text):
            return gen.generate(
                subject_prompt=text,
                subject_type=subject_type,
                base_url=base_url,
                api_key=api_key,
                model=model,
                reasoning_effort=reasoning_effort,
            )[0]

        results = [""] * MAX_SLOTS
        success, error = [], []
        reasons = {}
        empty = [i for i in range(1, MAX_SLOTS + 1) if i not in {k for k, _ in tasks}]

        ok = fail = 0
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, t): i for i, t in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    r = fut.result()
                    results[i - 1] = r
                    if r and not r.startswith("[Error"):
                        success.append(i)
                        ok += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 成功 {len(r)} 字 | {r[:40].strip()}...")
                    elif r == "":
                        error.append(i)
                        reasons[i] = "空响应（API 返回 200 但正文为空：降 reasoning_effort / 换 agnes-2.5-flash 后重试）"
                        fail += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 失败: 空响应（API 返回 200 但正文为空：降 reasoning_effort / 换 agnes-2.5-flash 后重试）")
                    else:
                        slot_reason = r.split("]", 1)[1].strip() if "]" in r else r
                        error.append(i)
                        reasons[i] = slot_reason or r
                        fail += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 失败: {slot_reason or r}")
                except Exception as e:
                    results[i - 1] = f"[Error] {e}"
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 三视图提示词批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 三视图提示词批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 三视图提示词批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))

        # 全三视图提示词 JSON：success 槽（升序）的成功提示词，失败/空槽不含；零成功=空串；可直连 三视图批量
        _ok_prompts = [results[i - 1] for i in success]
        all_turnaround_prompts = json.dumps(_ok_prompts, ensure_ascii=False, indent=2) if _ok_prompts else ""
        print(f"[Agnes 三视图提示词批量] all_turnaround_prompts: {len(_ok_prompts)} 条成功提示词 → JSON 输出（可连 Agnes 三视图批量生成）")

        return tuple(results) + (_status_json(success, error, empty, reason), all_turnaround_prompts)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundPromptBatch": AgnesTurnaroundPromptBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundPromptBatch": "✍️ Agnes 三视图提示词批量生成"}
