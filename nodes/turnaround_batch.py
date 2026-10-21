# -*- coding: utf-8 -*-
"""
Agnes 三视图批量生成节点
========================
与「Agnes 文本拆分」20 路输出一一对应的批量三视图出图节点：
20 个提示词输入槽，线程池并发请求图像 API（max_concurrency 限制同时
请求数，默认 10，超出排队），20 路 image + 1 路 status 输出（整批执行状态 JSON：
{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析；
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）。

- 空槽跳过：该槽不发请求，输出黑图占位 + [跳过] 状态
- 单槽失败不影响其他槽：该槽黑图占位 + [错误] 状态
- 每个工作线程各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型链路（资产线）：
  Agnes 资产提取.角色JSON ─▶ Agnes 文本拆分（JSON 数组，item_1..20）
      ─▶ Agnes 三视图提示词生成 × N（逐条扩写，输出可手工改）
      ─▶ Agnes 三视图批量生成（prompt_1..20）─▶ SaveImage / 参考图
  也可 LLM 对话一次性批量扩写 20 条定妆描述后手动填入各槽。
"""

import json
import torch
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..api import (
    AgnesClient,
    get_api_key,
    IMAGE_MODEL,
    AVAILABLE_IMAGE_MODELS,
    NEW_IMAGE_MODELS,
    pil_to_tensor,
)
from ._output_docs import OutputDocsMixin


MAX_SLOTS = 20
BLACK_W = 512
BLACK_H = 512


def _black_placeholder():
    """跳过/失败槽的占位黑图（每线程各建一张，不跨线程共享）"""
    return torch.zeros(1, BLACK_H, BLACK_W, 3)


class AgnesTurnaroundBatch(OutputDocsMixin):
    """三视图批量生成：20 路提示词并发出图（线程池，速率可限）"""

    DESCRIPTION = "三视图批量生成：20 个提示词输入对应文本拆分 20 路输出，线程池并发请求（max_concurrency 限制同时请求数，默认 10），输出 20 路 image + 1 路 status 整批状态 JSON（success/error/empty 槽号清单），空槽跳过，单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # 与单图三视图节点一致的推荐档位（横向宽幅，三视图少被裁切）
    QUALITIES = ("1K", "2K", "3K", "4K")
    ASPECT_RATIOS = ("1:1", "4:3", "3:2", "16:9", "21:9")

    # ── 输出：image_1..20 + status（共 21 槽）──
    RETURN_NAMES = tuple(f"image_{i}" for i in range(1, MAX_SLOTS + 1)) + ("status",)
    RETURN_TYPES = ("IMAGE",) * MAX_SLOTS + ("STRING",)
    RETURN_LABELS = tuple(f"三视图 {i}" for i in range(1, MAX_SLOTS + 1)) + ("执行状态 JSON",)
    OUTPUT_DOCS = {
        **{f"image_{i}": f"第 {i} 条提示词的三视图张量（可接 SaveImage 存档或作参考图；跳过/失败为黑图占位）"
           for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号],\"empty\":[空输入跳过槽号]}；"
            "成功槽的实际分辨率 WxH 见控制台日志；全部请求失败时额外含 \"reason\" 字段"
            "（各槽同一原因=字符串，不同=槽号→原因映射）；可直接连 Agnes 文本拆分（JSON 数组模式）"
            "拆成 3 条名单（成功/失败/空输入）做对接分析，或接 LLM 对话让模型解读哪些槽需要重试"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        prompts = {
            f"prompt_{i}": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": f"第 {i} 条三视图提示词（可连 文本拆分 item_{i} / 三视图提示词生成 输出）",
                "tooltip": f"第 {i} 条三视图提示词；留空=跳过该槽（不发请求，输出黑图占位）",
            })
            for i in range(1, MAX_SLOTS + 1)
        }
        prompts.update({
            "base_url": ("STRING", {
                "default": "",
                "placeholder": "https://api.agnes-ai.cn/v1",
                "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
            }),
            "api_key": ("STRING", {
                "default": "",
                "placeholder": "sk-...",
                "tooltip": "Agnes AI API Key，留空自动加载",
            }),
            "model": (AVAILABLE_IMAGE_MODELS, {
                "default": IMAGE_MODEL,
                "tooltip": "图像生成模型（agnes-image-2.5-flash 支持 1K-4K 档位）",
            }),
            "quality": (list(cls.QUALITIES), {
                "default": "2K",
                "tooltip": "画质档位：2K 性价比最高，4K 细节最清晰",
            }),
            "aspect_ratio": (list(cls.ASPECT_RATIOS), {
                "default": "21:9",
                "tooltip": "画面比例，三视图推荐宽幅（21:9 / 16:9），避免三个视图被裁切",
            }),
            "max_concurrency": ("INT", {
                "default": 10,
                "min": 1,
                "max": MAX_SLOTS,
                "step": 1,
                "tooltip": f"并发速率限制：线程池大小（同时请求数 1-{MAX_SLOTS}，默认 10）。非空提示词超过该值时排队执行；频繁 429/503 就调小",
            }),
        })
        return {"required": prompts, "optional": {}}

    def generate(self, prompt_1="", prompt_2="", prompt_3="", prompt_4="", prompt_5="",
                 prompt_6="", prompt_7="", prompt_8="", prompt_9="", prompt_10="",
                 prompt_11="", prompt_12="", prompt_13="", prompt_14="", prompt_15="",
                 prompt_16="", prompt_17="", prompt_18="", prompt_19="", prompt_20="",
                 base_url="", api_key="", model=IMAGE_MODEL, quality="2K",
                 aspect_ratio="21:9", max_concurrency=10):
        prompts = [prompt_1, prompt_2, prompt_3, prompt_4, prompt_5,
                   prompt_6, prompt_7, prompt_8, prompt_9, prompt_10,
                   prompt_11, prompt_12, prompt_13, prompt_14, prompt_15,
                   prompt_16, prompt_17, prompt_18, prompt_19, prompt_20]
        p = [str(x or "").strip() for x in prompts]
        max_conc = max(1, min(MAX_SLOTS, int(max_concurrency or 10)))

        def _status_json(success, error, empty, reason=None):
            data = {"success": success, "error": error, "empty": empty}
            # 全部请求失败（success 为空且 error 非空）→ 附失败原因：
            # 各槽同一原因=字符串；不同=槽号→原因 映射
            if reason is not None and not success and error:
                data["reason"] = reason
            return json.dumps(data, ensure_ascii=False, indent=2)

        # ── Key 解析 ──
        api_key = str(api_key or "").strip()
        if not api_key:
            api_key = str(get_api_key() or "").strip()
        if not api_key:
            reason = "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 三视图批量] [错误] {reason}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
            )

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(p, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 文本拆分 的 item_1..20 输出（上游先过 三视图提示词生成/LLM 扩写），或逐槽粘贴三视图提示词"
            print(f"[Agnes 三视图批量] {skip_msg}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], [], list(range(1, MAX_SLOTS + 1))),
            )

        # ── 尺寸参数（与单图三视图节点同逻辑）──
        if model in NEW_IMAGE_MODELS:
            size_arg, ratio_arg = quality.upper(), aspect_ratio
        else:
            size_arg = "2048x768" if aspect_ratio in ("21:9", "16:9") else "1024x1024"
            ratio_arg = None

        print(f"\n[Agnes 三视图批量] 共 {MAX_SLOTS} 槽，非空 {len(tasks)} 条，并发 {max_conc}")
        print(f"  模型: {model}, 档位: {quality}, 比例: {aspect_ratio}")

        # ── 每线程独立 client（Session 非线程安全）──
        def _worker(idx, text):
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                pils = client.generate_image(prompt=text, model=model,
                                             size=size_arg, ratio=ratio_arg, n=1)
            else:
                pils = client.generate_image(prompt=text, model=model,
                                             size=size_arg, n=1)
            if not pils:
                raise RuntimeError("服务器未返回图片")
            img = pils[0]
            if img.mode != "RGB":
                img = img.convert("RGB")
            return idx, pil_to_tensor(img), f"{img.size[0]}x{img.size[1]}"

        images = [None] * MAX_SLOTS
        success, error = [], []
        reasons = {}
        empty = [i for i in range(1, MAX_SLOTS + 1) if i not in {k for k, _ in tasks}]
        for i in empty:
            images[i - 1] = _black_placeholder()

        ok = fail = 0
        with ThreadPoolExecutor(max_workers=max_conc) as ex:
            futs = {ex.submit(_worker, i, t): i for i, t in tasks}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    _, tensor, res = fut.result()
                    images[i - 1] = tensor
                    success.append(i)
                    ok += 1
                    print(f"[Agnes 三视图批量] #{i} 成功 {res} | {p[i - 1][:40]}...")
                except Exception as e:
                    images[i - 1] = _black_placeholder()
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 三视图批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 三视图批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 三视图批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))

        return tuple(images) + (_status_json(success, error, empty, reason),)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundBatch": AgnesTurnaroundBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundBatch": "📐 Agnes 三视图批量生成"}
