# -*- coding: utf-8 -*-
"""
Agnes 三视图批量生成节点
========================
三视图提示词合并输入驱动的批量三视图出图节点：1 路 all_prompts 全文合并输入
（↔ 三视图提示词批量 all_turnaround_prompts 输出，一根线直连；也接受
单条三视图提示词纯文本，视为 1 条），线程池并发请求图像 API
（max_concurrency 限制同时请求数，默认 10，超出排队），
20 路 image + 1 路 status + 1 路 all_images 批量图张量输出（整批执行状态 JSON：
{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析；
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射；
all_images=成功槽按槽号升序堆叠的 (N,H,W,3) 批量张量，可直连 图像拼图
batch_images 总输入一根线出总览拼图）。

- 空槽跳过：该槽不发请求，输出黑图占位 + [跳过] 状态
- 单槽失败不影响其他槽：该槽黑图占位 + [错误] 状态
- all_prompts 解析（从上到下）：JSON 数组=逐条出图（最多 20 条，超出截断并
  日志标注；空项=跳过该槽，槽号保位）；JSON 字符串/单条纯文本=1 条；
  空输入=整批跳过（零 API 调用）
- 每个工作线程各建一个 AgnesClient（requests.Session 非线程安全，不复用）

典型链路（资产线，一根线到底）：
  Agnes 资产提取.角色JSON ─▶ Agnes 资产提示词批量生成（all_items）
      ─▶ all_prompts ─▶ Agnes 三视图提示词批量生成（all_prompts）
      ─▶ all_turnaround_prompts ─▶ Agnes 三视图批量生成（all_prompts）
      ─▶ all_images (N,H,W,3) ─▶ Agnes 图像拼图（batch_images）→ 总览拼图
  也可 LLM 对话一次性批量扩写 20 条定妆描述后手动粘贴 all_prompts。
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
    """三视图批量生成：all_prompts 合并输入（JSON 数组/纯文本）并发出三视图参考图（线程池，速率可限）+ 1 路 all_images 批量图张量 (N,H,W,3)"""

    DESCRIPTION = "三视图批量生成：all_prompts 合并输入（三视图提示词批量 all_turnaround_prompts 输出，JSON 数组从上到下逐条出图；单条三视图提示词纯文本也接受），线程池并发请求（max_concurrency 限制同时请求数，默认 10），输出 20 路 image + 1 路 status 整批状态 JSON（success/error/empty 槽号清单）+ 1 路 all_images 成功槽批量图张量 (N,H,W,3)（可直连 Agnes 图像拼图 batch_images 总输入一根线出总览），空槽跳过，单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # 与单图三视图节点一致的推荐档位（横向宽幅，三视图少被裁切）
    QUALITIES = ("1K", "2K", "3K", "4K")
    ASPECT_RATIOS = ("1:1", "4:3", "3:2", "16:9", "21:9")

    # ── 输出：image_1..20 + status + all_images（共 22 槽）──
    RETURN_NAMES = tuple(f"image_{i}" for i in range(1, MAX_SLOTS + 1)) + ("status", "all_images")
    RETURN_TYPES = ("IMAGE",) * MAX_SLOTS + ("STRING", "IMAGE")
    RETURN_LABELS = tuple(f"三视图 {i}" for i in range(1, MAX_SLOTS + 1)) + ("执行状态 JSON", "批量图 (N,H,W,3)")
    OUTPUT_DOCS = {
        **{f"image_{i}": f"第 {i} 条提示词（all_prompts 第 {i} 条）的三视图张量（可接 SaveImage 存档或作参考图；跳过/失败为黑图占位）"
           for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号],\"empty\":[空输入跳过槽号]}；"
            "槽号=all_prompts 条目序号（1 起，保位）；成功槽的实际分辨率 WxH 见控制台日志；"
            "全部请求失败时额外含 \"reason\" 字段（各槽同一原因=字符串，不同=槽号→原因映射）；"
            "可直接连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单（成功/失败/空输入）做对接分析，"
            "或接 LLM 对话让模型解读哪些槽需要重试"
        ),
        "all_images": (
            "成功槽按槽号升序堆叠的批量图张量 (N,H,W,3)：N=success 条数，同档位+比例出图 WxH 天然一致；"
            "失败/跳过槽不含（其黑图占位仍在 image_i 槽）；零成功=空批次 (0,512,512,3)；"
            "可直连 Agnes 图像拼图 batch_images 总输入（一根线出总览拼图，拼图内部自动跳黑图双保险）"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        prompts = {
            "all_prompts": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": '[\n  "full-body character turnaround sheet ...",\n  "three-view of a ..."\n]\n可连 Agnes 三视图提示词批量生成 all_turnaround_prompts 输出（JSON 数组，一根线直连）；\n也接受单条三视图提示词纯文本（连 three_view_prompt_i 或粘贴），视为 1 条',
                "tooltip": "三视图提示词合并输入：① JSON 数组（三视图提示词批量 all_turnaround_prompts 输出直连，条目从上到下逐条出图，最多 20 条，超出截断并日志标注；空项=跳过该槽，槽号保位）② 单条三视图提示词纯文本（连 三视图提示词批量 three_view_prompt_i 或手动粘贴，视为 1 条）③ 空=整批跳过（零 API 调用）",
            }),
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
                "tooltip": "图像生成模型（固定 agnes-image-2.5-flash，支持 1K-4K 档位）",
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
        return {
            "required": prompts,
            "optional": {
                "retries": ("INT", {
                    "label": "重试次数",
                    "default": 5,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "tooltip": "逐条生效的失败重试次数（0=不重试，单张请求一次即止）：503 生图队列满/429 限流分钟级退避（15/30/60/120s…），默认 5；整批最坏总时长≈条数×(1+重试次数)×请求超时",
                }),
                "timeout": ("INT", {
                    "label": "请求超时（秒）",
                    "default": 300,
                    "min": 30,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "单张 API 调用等待上限（秒），默认 300：大图档位/队列高峰期可拉高到 3600",
                }),
            },
        }

    @staticmethod
    def _parse_all_prompts(raw):
        """all_prompts 输入三档解析（从上到下）：
        ① JSON 数组 → 逐条（str 化、去空白；空项保留占位——槽号=条目位置）；
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

    def generate(self, all_prompts="", base_url="", api_key="", model=IMAGE_MODEL, quality="2K",
                 aspect_ratio="21:9", max_concurrency=10, retries=5, timeout=300):
        items, source, truncated = self._parse_all_prompts(all_prompts)
        p = items
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
        def _empty_batch():
            """零成功时的空批次 (0,512,512,3)（下游拼图按 N=0 全跳过处理）"""
            return torch.empty(0, BLACK_H, BLACK_W, 3)

        if not api_key:
            reason = "缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 三视图批量] [错误] {reason}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
                _empty_batch(),
            )

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(p, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 三视图提示词批量 的 all_turnaround_prompts 输出（JSON 数组），或连单条 three_view_prompt_i，或粘贴 JSON 数组/三视图提示词"
            print(f"[Agnes 三视图批量] {skip_msg}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], [], list(range(1, MAX_SLOTS + 1))),
                _empty_batch(),
            )

        # ── 尺寸参数（与单图三视图节点同逻辑）──
        if model in NEW_IMAGE_MODELS:
            size_arg, ratio_arg = quality.upper(), aspect_ratio
        else:
            size_arg = "2048x768" if aspect_ratio in ("21:9", "16:9") else "1024x1024"
            ratio_arg = None

        print(f"\n[Agnes 三视图批量] 输入={source}，条目 {len(p)}"
              + ("（超 20 条已截断）" if truncated else "")
              + f"，非空 {len(tasks)} 条，并发 {max_conc}")
        print(f"  模型: {model}, 档位: {quality}, 比例: {aspect_ratio}")

        # ── 每线程独立 client（Session 非线程安全）──
        def _worker(idx, text):
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                pils = client.generate_image(prompt=text, model=model,
                                             size=size_arg, ratio=ratio_arg, n=1,
                                             retries=retries, timeout=timeout)
            else:
                pils = client.generate_image(prompt=text, model=model,
                                             size=size_arg, n=1,
                                             retries=retries, timeout=timeout)
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

        # 批量图张量：成功槽按槽号升序堆叠 (N,H,W,3)（失败/跳过槽的黑图占位仍在 image_i 槽）；
        # 零成功=空批次 (0,512,512,3)；可直连 图像拼图 batch_images 总输入
        all_images = torch.cat([images[i - 1] for i in success], dim=0) if success else _empty_batch()
        print(f"[Agnes 三视图批量] all_images: {len(success)} 张成功图 → (N,H,W,3) 批量张量（可连 Agnes 图像拼图）")

        return tuple(images) + (_status_json(success, error, empty, reason), all_images)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundBatch": AgnesTurnaroundBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundBatch": "📐 Agnes 三视图批量生成"}
