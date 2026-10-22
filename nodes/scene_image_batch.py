# -*- coding: utf-8 -*-
"""
Agnes 分镜图批量生成节点
========================
「Agnes 分镜提示词批量生成」全提示词输出（all_prompts，JSON 数组）驱动的
分镜关键帧批量出图节点：1 路 all_prompts 全文合并输入（↔ 分镜提示词批量
all_prompts 输出，一根线直连；也接受单条英文提示词纯文本，视为 1 条），
线程池并发请求图像 API 批量出关键帧（max_concurrency 限制同时请求数，
默认 10，超出排队执行），50 路 image + 1 路 status 输出（整批执行状态 JSON：
{"success": [成功槽号], "error": [失败槽号], "empty": [空输入槽号]}，
可连 Agnes 文本拆分（JSON 数组模式）拆成 3 条名单做对接分析；
全部请求失败时额外含 "reason" 字段：各槽同一原因=字符串，不同=槽号→原因映射）。

- 空槽跳过：该槽不发请求，输出黑图占位（512×512）
- 单槽失败不影响其他槽：该槽黑图占位，原因见 status
- 每个工作线程各建一个 AgnesClient（requests.Session 非线程安全，不复用）
- 纯文生图：不接参考图——跨镜一致性（同一角色跨分镜长相）靠资产线参考图
  回流 图生图/关键帧生视频 节点解决，本节点负责"一次全出"

all_prompts 解析（从上到下）：JSON 数组=逐条处理（跳过空项，超 50 条截断并
日志标注）；JSON 字符串=1 条；非 JSON 纯文本（单条提示词直连/手动粘贴）=1 条；
空输入=整批跳过（零 API 调用）

下游注意：跳过/失败槽输出黑图占位且本节点是输出节点（image_i 可直接连
SaveImage/关键帧生视频）；接视频生成前请先用 status JSON 核对成功槽
（连 Agnes 文本拆分 JSON 数组模式拆 3 条名单，或 LLM 对话解读），
避免黑图/漏槽流入视频线。

典型接法（分镜线全量出图，一根线到底）：
  Agnes 总导演/场景切分（all_scenes JSON 数组）
      ─▶ Agnes 分镜提示词批量生成（all_scenes；+ 资产提取 5 路 JSON 任选注入）
      ─▶ all_prompts（全部提示词 JSON）─▶ Agnes 分镜图批量生成（all_prompts）
      ─▶ image_1..50（关键帧）─▶ SaveImage 存档 / 关键帧生视频（逐镜）
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


MAX_SLOTS = 50
BLACK_W = 512
BLACK_H = 512


def _black_placeholder():
    """跳过/失败槽的占位黑图（每线程各建一张，不跨线程共享）"""
    return torch.zeros(1, BLACK_H, BLACK_W, 3)


class AgnesSceneImageBatch(OutputDocsMixin):
    """分镜图批量生成：all_prompts 合并输入（JSON 数组/纯文本）并发出关键帧（线程池，速率可限）"""

    DESCRIPTION = "分镜图批量生成：all_prompts 合并输入（分镜提示词批量 all_prompts 输出，JSON 数组从上到下逐条出图；单条英文提示词纯文本也接受）整批并发请求图像 API 出关键帧（max_concurrency 限制同时请求数，默认 10），画质档位/宽高比可配（默认 16:9），输出 50 路 image + 1 路 status 整批状态 JSON（success/error/empty 槽号清单），空槽/失败槽黑图占位，单槽失败不影响其他槽"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # 关键帧默认宽幅电影画幅
    QUALITIES = ("1K", "2K", "3K", "4K")
    ASPECT_RATIOS = ("16:9", "21:9", "3:2", "4:3", "1:1", "9:16", "2:3", "3:4")

    # ── 输出：image_1..50 + status（共 51 槽）──
    RETURN_NAMES = tuple(f"image_{i}" for i in range(1, MAX_SLOTS + 1)) + ("status",)
    RETURN_TYPES = ("IMAGE",) * MAX_SLOTS + ("STRING",)
    RETURN_LABELS = tuple(f"分镜图 {i}" for i in range(1, MAX_SLOTS + 1)) + ("执行状态 JSON",)
    OUTPUT_DOCS = {
        **{f"image_{i}": f"第 {i} 条提示词（all_prompts 第 {i} 条）的关键帧张量（可接 SaveImage 存档或 关键帧生视频；跳过/失败/条目不足为黑图占位）"
           for i in range(1, MAX_SLOTS + 1)},
        "status": (
            "整批执行状态 JSON：{\"success\":[成功槽号],\"error\":[失败槽号],\"empty\":[空输入跳过槽号]}；"
            "槽号=all_prompts 条目序号（1 起），条目不足 50 时其余槽号进 empty；"
            "成功槽的实际分辨率 WxH 见控制台日志；全部请求失败时额外含 \"reason\" 字段"
            "（各槽同一原因=字符串，不同=槽号→原因映射）；可直接连 Agnes 文本拆分（JSON 数组模式）"
            "拆成 3 条名单（成功/失败/空输入）做对接分析，或接 LLM 对话让模型解读哪些槽需要重试"
        ),
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "all_prompts": ("STRING", {
                "multiline": True,
                "default": "",
                "placeholder": "[\n  \"a cinematic shot of ...\",\n  \"a close-up of ...\"\n]\n可连 Agnes 分镜提示词批量生成 all_prompts 输出（JSON 数组，从上到下逐条出图）；\n也接受单条英文提示词纯文本（连 分镜提示词生成 detailed_prompt_i 或粘贴），视为 1 条",
                "tooltip": "全提示词合并输入：① JSON 数组（分镜提示词批量 all_prompts 输出直连，条目从上到下逐条出图，最多 50 条，超出截断并日志标注；空项跳过）② 单条英文提示词纯文本（连 detailed_prompt_i 单路或手动粘贴，视为 1 条）③ 空=整批跳过（零 API 调用）",
            }),
            "quality": (list(cls.QUALITIES), {
                "default": "2K",
                "tooltip": "画质档位（整批共用）：2K 关键帧性价比最高；试跑用 1K 更省，4K 细节最清晰（仅新接口 agnes-image-2.5-flash 生效）",
            }),
            "aspect_ratio": (list(cls.ASPECT_RATIOS), {
                "default": "16:9",
                "tooltip": "画面比例（整批共用）：关键帧默认 16:9 电影画幅；漫剧竖屏选 9:16；旧接口 2.1/2.0 按宽幅 1920x1080 / 其他 1024x1024 出图",
            }),
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
                "tooltip": "图像生成模型（agnes-image-2.5-flash 支持 1K-4K 档位；2.1/2.0 旧版按像素出图）",
            }),
            "max_concurrency": ("INT", {
                "default": 10,
                "min": 1,
                "max": MAX_SLOTS,
                "step": 1,
                "tooltip": f"并发速率限制：线程池大小（同时请求数 1-{MAX_SLOTS}，默认 10）。非空提示词超过该值时排队执行；频繁 429/503 就调小",
            }),
        }
        return {"required": required, "optional": {}}

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

    def generate(self, all_prompts="", quality="2K", aspect_ratio="16:9",
                 base_url="", api_key="", model=IMAGE_MODEL, max_concurrency=10):
        items, source, truncated = self._parse_all_prompts(all_prompts)
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
            print(f"[Agnes 分镜图批量] [错误] {reason}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], list(range(1, MAX_SLOTS + 1)), [], reason),
            )

        # ── 全空跳过：一发请求都不发 ──
        tasks = [(i, t) for i, t in enumerate(items, 1) if t]
        if not tasks:
            skip_msg = "[跳过] 输入为空：请连接 Agnes 分镜提示词批量生成 的 all_prompts 输出（JSON 数组），或连单条 detailed_prompt_i，或粘贴 JSON 数组/英文提示词"
            print(f"[Agnes 分镜图批量] {skip_msg}")
            return tuple(_black_placeholder() for _ in range(MAX_SLOTS)) + (
                _status_json([], [], list(range(1, MAX_SLOTS + 1))),
            )

        # ── 尺寸参数（与单图节点同逻辑：新接口档位+比例，旧接口像素串）──
        if model in NEW_IMAGE_MODELS:
            size_arg, ratio_arg = quality.upper(), aspect_ratio
        else:
            size_arg = "1920x1080" if aspect_ratio in ("21:9", "16:9", "3:2", "4:3") else "1024x1024"
            ratio_arg = None

        print(f"\n[Agnes 分镜图批量] 输入={source}，条目 {len(tasks)}"
              + ("（超 50 条已截断）" if truncated else "")
              + f"，并发 {max_conc}")
        print(f"  模型: {model}, 档位: {quality}, 比例: {aspect_ratio}")

        # ── 每线程独立 client（Session 非线程安全）──
        def _worker(idx, text):
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            if model in NEW_IMAGE_MODELS:
                pils = client.generate_image(prompt=text, model=model,
                                             size=size_arg, ratio=ratio_arg, n=1)
            else:
                pils = client.generate_image(prompt=text, model=model, size=size_arg, n=1)
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
                    print(f"[Agnes 分镜图批量] #{i} 成功 {res} | {items[i - 1][:40]}...")
                except Exception as e:
                    images[i - 1] = _black_placeholder()
                    error.append(i)
                    reasons[i] = str(e) or type(e).__name__
                    fail += 1
                    print(f"[Agnes 分镜图批量] #{i} 失败: {e}")
        success.sort()
        error.sort()
        reason = None
        if not success and error:
            uniq = {reasons[i] for i in error}
            reason = uniq.pop() if len(uniq) == 1 else {str(i): reasons[i] for i in error}
        print(f"[Agnes 分镜图批量] 完成：成功 {ok}/{len(tasks)}，失败 {fail}（并发 {max_conc}）")
        print(f"[Agnes 分镜图批量] 状态: success={success} error={error} empty={empty}"
              + (f" reason={reason}" if reason is not None else ""))
        print(f"[Agnes 分镜图批量] 接 关键帧生视频 前请先核对 status：成功槽再放行，黑图占位槽勿连视频节点")

        return tuple(images) + (_status_json(success, error, empty, reason),)


NODE_CLASS_MAPPINGS = {"AgnesSceneImageBatch": AgnesSceneImageBatch}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesSceneImageBatch": "🎞️ Agnes 分镜图批量生成"}
