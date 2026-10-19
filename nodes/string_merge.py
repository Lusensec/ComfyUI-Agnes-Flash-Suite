"""
Agnes 字符串合并节点
=============
上下合并两个多行字符串：非空输入按顺序拼接（空字符串自动跳过，不产生多余空行），
适合把多段小说章节文本、多个节点输出文本合并成一个完整字符串。
"""

from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesStringMerge(OutputDocsMixin):
    """Agnes 字符串合并节点（纯文本处理，不调用 API）。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("result",)
    RETURN_LABELS = ("合并结果",)
    OUTPUT_DOCS = {
        "result": "上下合并后的字符串：非空输入按顺序拼接（空输入自动跳过，不产生多余空行/尾随分隔符）",
    }
    FUNCTION = "concat"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string_1": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "第一段字符串（上）...",
                    "tooltip": "第一段字符串（上方），支持多行文本；可连任意 STRING 输出",
                }),
                "string_2": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "第二段字符串（下）...",
                    "tooltip": "第二段字符串（下方），支持多行文本；可连任意 STRING 输出",
                }),
            },
            "optional": {
                "separator": ("STRING", {
                    "multiline": False,
                    "default": "\n",
                    "placeholder": "分隔符",
                    "tooltip": "两段之间的分隔符（默认一个换行；留空=直接首尾相接）。空输入被跳过时不产生尾随分隔符",
                }),
            },
        }

    def concat(self, string_1="", string_2="", separator="\n") -> Tuple[str]:
        parts = [s for s in ((string_1 or ""), (string_2 or "")) if s.strip()]
        sep = "\n" if separator is None else separator
        result = sep.join(parts)
        print(f"[Agnes 字符串合并] 合并 {len(parts)}/2 段，共 {len(result)} 字符")
        return (result,)


NODE_CLASS_MAPPINGS = {"AgnesStringMerge": AgnesStringMerge}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStringMerge": "🔗 Agnes 字符串合并"}
