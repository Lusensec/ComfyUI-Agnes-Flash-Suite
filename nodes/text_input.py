"""
Agnes 文本输入节点
===========
Agnes 专属字符串输入接口：手动输入/粘贴文本（小说章节内容、故事想法、
解说草稿、角色/场景描述等），从「文本」输出口直接喂给任何 Agnes 文本类节点
（LLM 对话、剧本生成、场景切分、分镜提示词生成……），
是整条 Agnes 管线的文本起点，替代灰色的通用 PrimitiveNode。

典型链路：
  Agnes 文本输入（章节内容） ──▶ Agnes LLM 对话（扩写/润色/改写）
  Agnes 文本输入（故事想法） ──▶ Agnes 剧本生成（想法 → 解说文案）
  Agnes 文本输入（章节内容） ──▶ Agnes 场景切分（→ 分镜提示词 → 生图/生视频）

纯输入节点：不调用 API、不需要 API Key；文本直接透传输出。
"""

from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesNovelTextSource(OutputDocsMixin):
    """Agnes 文本输入节点（纯字符串输入，不调用 API）。"""

    CATEGORY = "Agnes Novel"

    RETURN_NAMES = ("text",)
    RETURN_TYPES = ("STRING",)
    RETURN_LABELS = ("文本",)

    OUTPUT_DOCS = {
        "text": "输入的文本原样输出（未输入/未连接时为空字符串）。"
                "可接 Agnes LLM 对话 / 剧本生成 / 场景切分 / 分镜提示词生成 等任意文本类节点的输入",
    }

    FUNCTION = "get_text"
    # 非输出节点：作为管线起点，下游接了输出节点（保存视频/图像等）才会随图执行

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入小说章节内容，或故事想法 / 解说草稿 / 任意文本...\n"
                                   "例：第一章 苏尘睁开眼，发现自己回到了一切开始之前...",
                    "tooltip": "要输入的文本：小说章节、故事想法、人物/场景描述等。"
                               "「文本」输出可直连 Agnes LLM 对话、剧本生成、场景切分等文本类节点",
                }),
            },
            "optional": {},
        }

    def get_text(self, text="") -> Tuple[str]:
        text = text or ""
        if text.strip():
            print(f"[Agnes 文本输入] 就绪：{len(text)} 字")
        else:
            print("[Agnes 文本输入] 未输入文本：输出为空字符串（可被下游节点跳过或按空处理）")
        return (text,)


NODE_CLASS_MAPPINGS = {"AgnesNovelTextSource": AgnesNovelTextSource}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelTextSource": "📥 Agnes 文本输入"}
