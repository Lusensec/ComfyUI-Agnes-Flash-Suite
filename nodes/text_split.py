"""
Agnes 文本拆分节点
============
把一段文本（资产 JSON 列表 / LLM 输出的【名】分块 / 编号列表 / 多段文本）
拆成最多 20 路独立字符串，方便逐条喂给 三视图生成、文生图、LLM 对话 等节点，
实现「一个角色/道具/场景 = 一张图」的批量资产出图。

典型链路（资产线）：
  Agnes 资产提取.角色JSON ──▶ [可选] LLM 对话（把 JSON 逐条扩写成定妆描述）
      ──▶ Agnes 文本拆分（选「JSON 数组」或「【】括号块」模式）
      ──▶ 拆分 1~12 ──▶ Agnes 三视图生成（subject_type=角色，可再接 reference_image 保一致）
纯文本处理节点，不需要 API Key。
"""

import json
import re
from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesTextSplitter(OutputDocsMixin):
    """Agnes 文本拆分节点（纯文本处理，不调用 API）。"""

    CATEGORY = "Agnes Novel"

    SPLIT_MODES = ("JSON 数组", "JSON 对象", "【】括号块", "编号列表", "空行段落")
    MAX_SLOTS = 20

    RETURN_NAMES = tuple(f"item_{i}" for i in range(1, MAX_SLOTS + 1)) + ("count", "text_out",)
    RETURN_TYPES = ("STRING",) * (MAX_SLOTS + 2)
    RETURN_LABELS = (
        tuple(f"第 {i} 条" for i in range(1, MAX_SLOTS + 1))
        + ("条数（超过 12 会标注）", "原文透传",)
    )

    OUTPUT_DOCS = {
        **{f"item_{i}": f"拆分后的第 {i} 条独立文本（供 三视图/文生图/LLM 对话 逐条使用；超出 20 条不显示）"
           for i in range(1, MAX_SLOTS + 1)},
        "count": "实际拆分出的条目总数（超过 20 条时显示为「N（仅显示前 20 条）」）",
        "text_out": "原始输入文本透传（方便并联其他节点或存档）",
    }

    FUNCTION = "split"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": '粘贴/连接要拆分的文本...\n例：JSON 数组 [{"name":"苏尘","desc":"..."}, ...]\n或 LLM 输出【苏尘】...【柳如烟】... 格式',
                    "tooltip": "要拆分的完整文本。可连：资产提取的任意 JSON 输出 / LLM 对话的回复输出 / 手动粘贴。按下方拆分模式解析成独立条目",
                }),
                "mode": (list(cls.SPLIT_MODES), {
                    "default": "JSON 数组",
                    "tooltip": "拆分模式：「JSON 数组」= 每个 JSON 对象/元素一条（资产提取输出的直接可用）；"
                               "「JSON 对象」= 逐键一条（键: 值），批量节点 status 输出（success/error/empty）直接拆成 3 条名单；"
                               "「【】括号块」= 每个【名】起头到下一个【前」（LLM 输出的定妆文常用此格式）；"
                               "「编号列表」= 每行以 1. / 1、/ 一、 等编号起头；「空行段落」= 空行分隔的段落",
                }),
            },
            "optional": {},
        }

    # ---------- 各模式解析 ----------

    @classmethod
    def _split_json(cls, text: str):
        data = json.loads(text)
        items = data
        if isinstance(data, dict):
            # 资产提取常见 {"characters": [...]}/{"locations": [...]} 形式 → 取第一个列表值
            for v in data.values():
                if isinstance(v, list):
                    items = v
                    break
            else:
                items = [data]
        if not isinstance(items, list):
            items = [items]
        return [json.dumps(it, ensure_ascii=False, indent=2) for it in items]

    @classmethod
    def _split_json_object(cls, text: str):
        # 批量节点 status 输出形如 {"success":[1,2],"error":[3],"empty":[4]}：
        # 逐 key 一条（"key: [值]"），3 个 key → 3 条名单，供 文本拆分/LLM 对接分析
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("不是 JSON 对象（键值对）")
        return [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items()]

    @classmethod
    def _split_brackets(cls, text: str):
        # 每个【...】块：从【起，到下一个【前
        blocks = re.findall(r'【[^】\n]+】.*?(?=\n\s*【[^】\n]+】|\Z)', text, re.S)
        return [b.strip() for b in blocks if b.strip()]

    @classmethod
    def _split_numbered(cls, text: str):
        # 行首 1. / 1、/ 一、 / (1) 等编号 → 逐行条目
        parts = re.split(r'(?m)^\s*(?:\d+\s*[\.、\)）:：]|[一二三四五六七八九十百]+\s*[、\.．]|\(\d+\))\s*', text)
        return [p.strip() for p in parts if p and p.strip()]

    @classmethod
    def _split_paragraphs(cls, text: str):
        parts = re.split(r'\n\s*\n+', text)
        return [p.strip() for p in parts if p.strip()]

    def split(self, text="", mode="JSON 数组") -> Tuple[str, ...]:
        text = text or ""
        items = []
        if text.strip():
            handlers = {
                "JSON 数组": self._split_json,
                "JSON 对象": self._split_json_object,
                "【】括号块": self._split_brackets,
                "编号列表": self._split_numbered,
                "空行段落": self._split_paragraphs,
            }
            handler = handlers.get(mode, handlers["JSON 数组"])
            try:
                items = handler(text)
            except Exception as e:
                items = []
                print(f"[Agnes Text Split] {mode} 模式解析失败：{e}")

        slots = list(items[: self.MAX_SLOTS]) + [""] * (self.MAX_SLOTS - min(len(items), self.MAX_SLOTS))
        total = len(items)
        count = f"{total}（仅显示前 {self.MAX_SLOTS} 条）" if total > self.MAX_SLOTS else str(total)
        print(f"[Agnes Text Split] {mode} 模式：拆出 {total} 条")
        return tuple(slots) + (count, text)


NODE_CLASS_MAPPINGS = {"AgnesTextSplitter": AgnesTextSplitter}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTextSplitter": "✂️ Agnes 文本拆分"}
