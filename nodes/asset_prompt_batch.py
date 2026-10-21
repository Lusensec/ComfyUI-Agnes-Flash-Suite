# -*- coding: utf-8 -*-
"""
Agnes 资产提示词批量生成节点
===========================
与「Agnes 文本拆分」20 路输出一一对应的资产提示词批量生成节点：
20 个资产 JSON 输入槽（asset_1..20 ↔ 文本拆分 item_1..20），线程池并发
请求文本 API（max_concurrency 限制同时请求数，默认 10，超出排队执行），
20 路 english_prompt + 1 路 status 输出（整批执行状态 JSON：
{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析；
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）。

- 参数与单条「Agnes 资产提示词生成」完全一致（subject_type/style/base_url/
  api_key/model/reasoning_effort），20 槽共用，另加 max_concurrency 速率限制
- 空槽跳过：该槽不发请求，输出空字符串
- 单槽失败不影响其他槽：该槽输出 [Error] 前缀文本
- 每个工作线程内部各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型接法（资产线）：
  Agnes 资产提取.角色JSON ─▶ Agnes 文本拆分（JSON 数组，item_1..20）
      ─▶ Agnes 资产提示词批量生成（asset_1..20）
      ─▶ english_prompt_1..20 ─▶ Agnes 文生图 / 三视图生成(subject_desc)
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import (
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
)
from .asset_prompt import AgnesAssetPromptGenerator, SUBJECT_TYPES, STYLE_OPTIONS
from ._output_docs import OutputDocsMixin


MAX_SLOTS = 20


class AgnesAssetPromptBatch(OutputDocsMixin):
    """资产提示词批量生成：20 路资产 JSON 并发生成英文提示词 + 1 路整批状态 JSON（线程池，速率可限）"""

    DESCRIPTION = "资产提示词批量生成：20 个资产 JSON 输入对应文本拆分 20 路输出，线程池并发请求（max_concurrency 限制同时请求数，默认 10），输出 20 路 english_prompt + 1 路 status 整批状态 JSON（success/error/empty 槽号清单），单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：english_prompt_1..20 + status（共 21 槽）──
    RETURN_NAMES = tuple(f"english_prompt_{i}" for i in range(1, MAX_SLOTS + 1)) + ("status",)
    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 1)
    RETURN_LABELS = tuple(f"英文资产提示词 {i}" for i in range(1, MAX_SLOTS + 1)) + ("执行状态 JSON",)
    OUTPUT_DOCS = {
        **{f"english_prompt_{i}": (
            f"第 {i} 条资产的英文生图提示词（保留 JSON 全部描述字段 + 主体构图指令 + 风格尾词 + quality 词，"
            f"可直接接 文生图/三视图生成(subject_desc)；空输入=空字符串；失败=[Error] 前缀文本"
        ) for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号，含空响应],\"empty\":[空输入跳过槽号]}；"
            "全部请求失败时额外含 \"reason\" 字段（各槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，"
            "或接 LLM 对话让模型解读哪些槽需要重试"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            f"asset_{i}": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": f'第 {i} 条资产 JSON（可连 文本拆分 item_{i} / 资产提取 输出）',
                "tooltip": f"第 {i} 条资产 JSON；留空=跳过该槽（不发请求，输出空字符串）",
            })
            for i in range(1, MAX_SLOTS + 1)
        }
        required.update({
            "subject_type": (list(SUBJECT_TYPES), {
                "default": "角色",
                "tooltip": "主体类型（决定构图指令，20 槽共用）：角色=全身设定图 / 物品道具=特写静物 / 服装=定妆服装图 / 场景=全景建立镜头 / 载具=四分之三视角 / 通用",
            }),
            "style": (list(STYLE_OPTIONS), {
                "default": "cinematic",
                "tooltip": "生图风格尾词（20 槽共用）：cinematic=电影感 / anime=动漫 / realistic=写实 / watercolor=水彩 / oil_painting=油画",
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
                "tooltip": f"并发速率限制：线程池大小（同时请求数 1-{MAX_SLOTS}，默认 10）。非空资产 JSON 超过该值时排队执行；频繁 429/503 就调小",
            }),
        })
        return {"required": required, "optional": {}}

    def generate(self, asset_1="", asset_2="", asset_3="", asset_4="", asset_5="",
                 asset_6="", asset_7="", asset_8="", asset_9="", asset_10="",
                 asset_11="", asset_12="", asset_13="", asset_14="", asset_15="",
                 asset_16="", asset_17="", asset_18="", asset_19="", asset_20="",
                 subject_type="角色", style="cinematic",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_concurrency=10):
        assets = [asset_1, asset_2, asset_3, asset_4, asset_5,
                  asset_6, asset_7, asset_8, asset_9, asset_10,
                  asset_11, asset_12, asset_13, asset_14, asset_15,
                  asset_16, asset_17, asset_18, asset_19, asset_20]
        a = [str(x or "").strip() for x in assets]
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
            print(f"[Agnes 资产提示词批量] {msg}")
            return tuple(msg for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
            )

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(a, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入全部为空：请连接 Agnes 文本拆分 的 item_1..20 输出，或逐槽粘贴资产 JSON"
            print(f"[Agnes 资产提示词批量] {skip_msg}")
            return ("",) * MAX_SLOTS + (_status_json([], [], list(range(1, MAX_SLOTS + 1))),)

        print(f"\n[Agnes 资产提示词批量] 共 {MAX_SLOTS} 槽，非空 {len(tasks)} 条，并发 {max_conc}")
        print(f"  模型: {model}, 主体类型: {subject_type}, 风格: {style}")

        # 复用单条节点的成熟逻辑（每线程内各建 AgnesClient，Session 非线程安全不复用）
        gen = AgnesAssetPromptGenerator()

        def _worker(idx, text):
            return gen.generate(
                asset_json=text,
                subject_type=subject_type,
                style=style,
                base_url=base_url,
                api_key=api_key,
                model=model,
                reasoning_effort=reasoning_effort,
            )[0]

        prompts = [""] * MAX_SLOTS
        success, error = [], []
        reasons = {}
        empty = [i for i in range(1, MAX_SLOTS + 1) if i not in {k for k, _ in tasks}]

        ok = fail = 0
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, t): i for i, t in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    p = fut.result()
                    prompts[i - 1] = p
                    if p and not p.startswith("[Error"):
                        success.append(i)
                        ok += 1
                        print(f"[Agnes 资产提示词批量] #{i} 成功 {len(p)} 字 | {p[:40].strip()}...")
                    elif p == "":
                        error.append(i)
                        reasons[i] = "空响应（API 返回 200 但正文为空：降 reasoning_effort / 换 agnes-2.5-flash 后重试）"
                        fail += 1
                        print(f"[Agnes 资产提示词批量] #{i} 失败: 空响应（API 返回 200 但正文为空：降 reasoning_effort / 换 agnes-2.5-flash 后重试）")
                    else:
                        slot_reason = p.split("]", 1)[1].strip() if "]" in p else p
                        error.append(i)
                        reasons[i] = slot_reason or p
                        fail += 1
                        print(f"[Agnes 资产提示词批量] #{i} 失败: {slot_reason or p}")
                except Exception as e:
                    prompts[i - 1] = f"[Error] {e}"
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 资产提示词批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 资产提示词批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 资产提示词批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))

        return tuple(prompts) + (_status_json(success, error, empty, reason),)


NODE_CLASS_MAPPINGS = {"AgnesAssetPromptBatch": AgnesAssetPromptBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetPromptBatch": "🖌️ Agnes 资产提示词批量生成"}
