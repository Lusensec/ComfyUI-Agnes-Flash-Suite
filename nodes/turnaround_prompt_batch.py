# -*- coding: utf-8 -*-
"""
Agnes 三视图提示词批量生成节点
==============================
与「Agnes 文本拆分」20 路输出一一对应的三视图提示词批量生成节点：
20 个资产提示词输入槽（prompt_1..20 ↔ 资产提示词批量 english_prompt_1..20），
线程池并发生成三视图英文提示词（max_concurrency 限制同时请求数，默认 10，
超出排队执行），20 路 three_view_prompt + 20 路 status 输出（成功/跳过/错误，
各槽状态一目了然）。

- 参数与单条「Agnes 三视图提示词生成」完全一致（subject_type/base_url/
  api_key/model/reasoning_effort），20 槽共用，另加 max_concurrency 速率限制
- 空槽跳过：该槽不发请求，输出空字符串
- 单槽失败不影响其他槽：该槽输出 [Error] 前缀文本
- 每个工作线程内部各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型接法（资产线）：
  Agnes 资产提取.角色JSON ─▶ Agnes 文本拆分（JSON 数组，item_1..20）
      ─▶ Agnes 资产提示词批量生成（asset_1..20）
      ─▶ Agnes 三视图提示词批量生成（prompt_1..20 ↔ english_prompt_1..20）
      ─▶ three_view_prompt_1..20 ─▶ Agnes 三视图生成(subject_desc)
"""

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
    """三视图提示词批量生成：20 路资产提示词并发生成三视图英文提示词 + 20 路状态输出（线程池，速率可限）"""

    DESCRIPTION = "三视图提示词批量生成：20 个资产提示词输入对应 资产提示词批量 20 路输出，线程池并发请求（max_concurrency 限制同时请求数，默认 10），输出 20 路 three_view_prompt + 20 路 status（成功=成功 N 字；空输入=[跳过]；失败=[错误]），单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：three_view_prompt_1..20 + status_1..20（共 40 槽）──
    RETURN_NAMES = (
        tuple(f"three_view_prompt_{i}" for i in range(1, MAX_SLOTS + 1))
        + tuple(f"status_{i}" for i in range(1, MAX_SLOTS + 1))
    )
    RETURN_TYPES = ("STRING",) * MAX_SLOTS * 2
    RETURN_LABELS = (
        tuple(f"三视图提示词 {i}" for i in range(1, MAX_SLOTS + 1))
        + tuple(f"状态 {i}" for i in range(1, MAX_SLOTS + 1))
    )
    OUTPUT_DOCS = {
        **{f"three_view_prompt_{i}": (
            f"第 {i} 条资产提示词的完整三视图英文提示词（主体全部细节 + 分栏布局（左 1/3 特写 + 右 2/3 三视图）"
            f"+ 虚幻引擎渲染/PBR/柔和漫射光 + 纯白背景干净极简无阴影 + 8K 质量尾词，"
            f"可直接接 三视图生成(subject_desc)；空输入=空字符串；失败=[Error] 前缀文本"
        ) for i in range(1, MAX_SLOTS + 1)},
        **{f"status_{i}": (
            f"第 {i} 槽执行状态：成功=成功 N 字；空输入=[跳过] 输入为空；失败=[错误] 原因；"
            f"API 200 但正文为空=[错误] 空响应（常见为思考预算耗尽）"
        ) for i in range(1, MAX_SLOTS + 1)},
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            f"prompt_{i}": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": f"第 {i} 条资产提示词（可连 资产提示词批量 english_prompt_{i} / 资产提示词生成 输出）",
                "tooltip": f"第 {i} 条资产提示词（英文/中文均可）；留空=跳过该槽（不发请求，输出空字符串）",
            })
            for i in range(1, MAX_SLOTS + 1)
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

    def generate(self, prompt_1="", prompt_2="", prompt_3="", prompt_4="", prompt_5="",
                 prompt_6="", prompt_7="", prompt_8="", prompt_9="", prompt_10="",
                 prompt_11="", prompt_12="", prompt_13="", prompt_14="", prompt_15="",
                 prompt_16="", prompt_17="", prompt_18="", prompt_19="", prompt_20="",
                 subject_type="角色",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_concurrency=10):
        prompts = [prompt_1, prompt_2, prompt_3, prompt_4, prompt_5,
                   prompt_6, prompt_7, prompt_8, prompt_9, prompt_10,
                   prompt_11, prompt_12, prompt_13, prompt_14, prompt_15,
                   prompt_16, prompt_17, prompt_18, prompt_19, prompt_20]
        p = [str(x or "").strip() for x in prompts]
        max_conc = max(1, min(MAX_SLOTS, int(max_concurrency or 10)))

        # ── Key 解析 ──
        api_key = str(api_key or "").strip()
        if not api_key:
            api_key = str(get_api_key() or "").strip()
        if not api_key:
            msg = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 三视图提示词批量] {msg}")
            return tuple(msg for _ in range(MAX_SLOTS)) + tuple(msg for _ in range(MAX_SLOTS))

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(p, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入全部为空：请连接 资产提示词批量 的 english_prompt_1..20 输出（或 资产提示词生成 逐槽），或逐槽粘贴提示词"
            print(f"[Agnes 三视图提示词批量] {skip_msg}")
            return ("",) * MAX_SLOTS + tuple(skip_msg for _ in range(MAX_SLOTS))

        print(f"\n[Agnes 三视图提示词批量] 共 {MAX_SLOTS} 槽，非空 {len(tasks)} 条，并发 {max_conc}")
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
        statuses = [""] * MAX_SLOTS
        task_ids = {i for i, _ in tasks}
        for i in range(1, MAX_SLOTS + 1):
            if i not in task_ids:
                statuses[i - 1] = "[跳过] 输入为空"

        ok = fail = 0
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, t): i for i, t in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    r = fut.result()
                    results[i - 1] = r
                    if r and not r.startswith("[Error"):
                        statuses[i - 1] = f"成功 {len(r)} 字"
                        ok += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 成功 {len(r)} 字 | {r[:40].strip()}...")
                    elif r == "":
                        statuses[i - 1] = "[错误] 空响应（API 返回 200 但正文为空：降 reasoning_effort / 换 agnes-2.5-flash 后重试）"
                        fail += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 失败: 空响应")
                    else:
                        reason = r.split("]", 1)[1].strip() if "]" in r else r
                        statuses[i - 1] = f"[错误] {reason or r}"
                        fail += 1
                        print(f"[Agnes 三视图提示词批量] #{i} 失败: {reason or r}")
                except Exception as e:
                    results[i - 1] = f"[Error] {e}"
                    statuses[i - 1] = f"[错误] {e}"
                    fail += 1
                    print(f"[Agnes 三视图提示词批量] #{i} 失败: {e}")
        print(f"[Agnes 三视图提示词批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")

        return tuple(results) + tuple(statuses)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundPromptBatch": AgnesTurnaroundPromptBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundPromptBatch": "✍️ Agnes 三视图提示词批量生成"}
