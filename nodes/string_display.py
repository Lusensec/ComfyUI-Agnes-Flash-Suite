# -*- coding: utf-8 -*-
"""
Agnes 字符串展示节点
==================
纯展示/观测节点（不调 API、不要 Key、无任何配置输入）：
把连入的字符串显示在**节点身体内**（前端扩展动态创建的只读文本区，
重载工作流时恢复上次显示内容），执行时打一条控制台日志。
输出 text_out 原样透传，可直接接下一个节点（可一对多）。

上屏机制（仿 ComfyUI-Custom-Scripts 的 Show Text，三件套）：
  ① Python 端 ui 回写：return {"ui": {"text": text}, "result": (text,)}，
     核心执行引擎把 ui 部分随 "executed" 推送给前端 → 调用 node.onExecuted({text})
  ② 前端扩展 web/js/agnes-string-display.js 钩 onExecuted，
     在节点身体内动态创建只读多行控件显示文本，并自动撑大节点
  ③ 持久化：执行时把 node["widgets_values"]=[text] 写回工作流内存（extra_pnginfo），
     保存/重载工作流后由 ② 的 onConfigure 钩子从存档恢复上次显示
前端缺 legacy shim（无 scripts/app.js 的纯 Vue 环境）时 ② 文件加载失败，
自动退化为「仅控制台日志」，透传功能不受影响。

接法示例：
  任意文本输出（文本拆分 / 总导演 / 资产提取 / LLM 对话...）
      → Agnes 字符串展示 → 下一节点（或终端展示）
"""

from ._output_docs import OutputDocsMixin


class AgnesStringDisplay(OutputDocsMixin):
    """字符串展示：在节点身体内显示连入的字符串，并原样透传给下一个节点"""

    DESCRIPTION = "字符串展示：在节点身体内显示连入的字符串（只读文本区，重载可恢复）+ 控制台日志，透传输出可接下一个节点；不调 API、不需要 Key"

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
                    "tooltip": "要展示的字符串：必须连上游节点的文本输出（不可手工填写，本节点没有任何配置输入）；空串也允许透传；执行后在节点身体内显示",
                }),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
            "optional": {},
        }

    def display(self, text: str = "", unique_id=None, extra_pnginfo=None) -> dict:
        text = text or ""
        preview = (text[:120] + ("..." if len(text) > 120 else "")).replace("\n", "⏎")
        print(f"[Agnes String] 展示（{len(text)} 字符）: {preview}")
        if not text:
            print("[Agnes String] （空字符串，原样透传）")

        # 持久化：把本次显示文本写回内存工作流中本节点的 widgets_values，
        # 用户保存并重新加载工作流后，前端扩展可从存档恢复上次的身体显示
        if unique_id is not None and extra_pnginfo is not None:
            try:
                if (isinstance(extra_pnginfo, list) and extra_pnginfo
                        and isinstance(extra_pnginfo[0], dict)
                        and "workflow" in extra_pnginfo[0]):
                    workflow = extra_pnginfo[0]["workflow"]
                    uid = unique_id[0] if isinstance(unique_id, (list, tuple)) else unique_id
                    node = next(
                        (x for x in workflow.get("nodes", []) if str(x.get("id")) == str(uid)),
                        None,
                    )
                    if node is not None:
                        node["widgets_values"] = [text]
            except Exception:
                pass  # 写回失败不影响显示与透传

        # ui 回写：核心执行引擎推给前端 → node.onExecuted({text}) → 前端扩展上屏
        return {"ui": {"text": text}, "result": (text,)}


NODE_CLASS_MAPPINGS = {"AgnesStringDisplay": AgnesStringDisplay}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStringDisplay": "📄 Agnes 字符串展示"}
