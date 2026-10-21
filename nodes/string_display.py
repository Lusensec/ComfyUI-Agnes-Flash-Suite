# -*- coding: utf-8 -*-
"""
Agnes 字符串展示节点
==================
纯展示/观测节点（不调 API、不要 Key、无任何配置输入）：
把连上来的字符串直接展示在节点面板（多行渲染），执行时打一条控制台日志，
输出 text_out 原样透传，可直接接下一个节点（可一对多）。

定位：Agnes 配色版的「Show Text」——管线中间文本的观测点。
不参与 配置/文本/图片/视频 四大类分级，前端配色表给予独立的
展示类色（玫红），一眼区别于所有功能类节点。

接法示例：
  任意文本输出（文本拆分 / 总导演 / 资产提取 / LLM 对话...）
      → Agnes 字符串展示 → 下一节点（或终端展示）
"""

from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesStringDisplay(OutputDocsMixin):
    """字符串展示：显示连入的字符串，并原样透传给下一个节点"""

    DESCRIPTION = "字符串展示：显示连入的字符串（节点面板可见 + 控制台日志），透传输出可接下一个节点；不调 API、不需要 Key"

    CATEGORY = "Agnes Novel"
    FUNCTION = "display"
    OUTPUT_NODE = True

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text_out",)
    RETURN_LABELS = ("字符串透传",)
    OUTPUT_DOCS = {
        "text_out": "输入字符串原样透传（不做任何修改），可接任意 STRING 下游，支持一对多连线；空串也照传",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "forceInput": True,
                    "placeholder": "要展示的字符串...",
                    "tooltip": "要展示的字符串：必须连上游节点的文本输出（不可手工填写，本节点没有任何配置输入）；空串也允许透传",
                }),
            },
            "optional": {},
        }

    def display(self, text: str = "") -> Tuple[str]:
        text = text or ""
        preview = (text[:120] + ("..." if len(text) > 120 else "")).replace("\n", "⏎")
        print(f"[Agnes String] 展示（{len(text)} 字符）: {preview}")
        if not text:
            print("[Agnes String] （空字符串，原样透传）")
        return (text,)


NODE_CLASS_MAPPINGS = {"AgnesStringDisplay": AgnesStringDisplay}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStringDisplay": "📄 Agnes 字符串展示"}
