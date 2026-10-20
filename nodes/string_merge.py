"""
Agnes 字符串合并节点
=============
上/中/下合并三个多行字符串：非空段落按 上→中→下 顺序拼接（空段落自动跳过，不产生多余空行），
适合把多段小说章节文本、多个节点输出文本合并成一个完整字符串；
「中段」槽专为**人工衔接语**设计：两段提示词之间手输一句过渡/连接描述（或连其他文本节点输出）。
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
        "result": "上/中/下合并后的字符串：非空段落按 上→中→下 顺序拼接（空段落自动跳过，不产生多余空行/尾随分隔符）",
    }
    FUNCTION = "concat"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            # 前端控件顺序 = required 组在前、optional 组在后（各自按声明顺序）；
            # 分组 [string_1, string_3] + [string_2, separator] ⇒ 面板自上而下：
            # 第一段（上）→ 第二段（中）→ 第三段（下）→ 分隔符
            "required": {
                "string_1": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "第一段字符串（上）...",
                    "tooltip": "第一段字符串（上），支持多行文本；可连任意 STRING 输出",
                }),
                "string_3": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "第二段字符串（中）：人工衔接语，如「随后镜头缓缓推进至…」，或连 LLM 对话/文本节点输出",
                    "tooltip": "第二段字符串（中，上、下之间的人工衔接语）：手输一句过渡/连接描述，或连任意 STRING 输出；留空=上、下直接合并",
                }),
            },
            "optional": {
                "string_2": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "第三段字符串（下）...",
                    "tooltip": "第三段字符串（下），支持多行文本；可连任意 STRING 输出",
                }),
                "separator": ("STRING", {
                    "multiline": False,
                    "default": "\n",
                    "placeholder": "分隔符",
                    "tooltip": "段落之间的分隔符（默认一个换行；留空=直接首尾相接）。空段落被跳过时不产生尾随分隔符",
                }),
            },
        }

    def concat(self, string_1="", string_2="", separator="\n", string_3="") -> Tuple[str]:
        parts = [s for s in ((string_1 or ""), (string_3 or ""), (string_2 or "")) if s.strip()]
        sep = "\n" if separator is None else separator
        result = sep.join(parts)
        print(f"[Agnes 字符串合并] 合并 {len(parts)}/3 段，共 {len(result)} 字符")
        return (result,)


NODE_CLASS_MAPPINGS = {"AgnesStringMerge": AgnesStringMerge}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStringMerge": "🔗 Agnes 字符串合并"}
