# -*- coding: utf-8 -*-
"""
OutputDocsMixin：节点输出描述共享 Mixin
========================================
ComfyUI 节点规格中，输入参数（widgets）有 tooltip/label 描述机制。
输出侧有两个官方扩展点，本 mixin 同时补齐：

1. **OUTPUT_TOOLTIPS**（节点类属性，与 RETURN_NAMES 一一对应）
   ComfyUI 内核 server.py 会读取该属性并以 `output_tooltips` 字段随节点定义
   下发给前端——节点文档面板（右侧"输出"表格）"描述"列、以及
   输出 socket 的悬停提示，读的就是这个字段。未定义时面板显示 "-"。

2. **get_extra_output_methods / get_extra_pnginfo**
   保存图像/视频（或连接支持 pnginfo 的节点）时，会把类属性
   OUTPUT_DOCS 中的各输出说明写入文件元数据，便于在 ComfyUI 画廊、
   PNG info 查看器中理解每个输出的含义与去向。

用法：
    class MyNode(OutputDocsMixin):
        RETURN_NAMES = ("images", "status",)
        OUTPUT_DOCS = {
            "images": "生成的图像张量（连接 SaveImage 或视频节点参考）",
            "status": "处理状态（复用/生成/错误信息）",
        }
        # OUTPUT_TOOLTIPS 由 mixin 元类自动从 RETURN_NAMES + OUTPUT_DOCS 生成
"""


class _OutputDocsMeta(type):
    """类创建时自动把 OUTPUT_DOCS 展开为 OUTPUT_TOOLTIPS（与 RETURN_NAMES 对齐）。"""

    def __new__(mcs, name, bases, ns):
        cls = super().__new__(mcs, name, bases, ns)
        docs = ns.get("OUTPUT_DOCS")
        names = ns.get("RETURN_NAMES")
        # 仅在类自身定义了 OUTPUT_DOCS 且未显式声明 OUTPUT_TOOLTIPS 时生成
        if docs and names and "OUTPUT_TOOLTIPS" not in ns:
            cls.OUTPUT_TOOLTIPS = tuple(docs.get(n, "") for n in names)
        return cls


class OutputDocsMixin(metaclass=_OutputDocsMeta):
    """为节点提供统一的输出描述机制（UI 提示 + pnginfo 元数据）。"""

    #: 输出名 -> 描述。子类覆盖。
    OUTPUT_DOCS = {}

    @classmethod
    def get_extra_output_methods(cls):
        """合并父类已声明的扩展方法，避免重复。"""
        methods = []
        for base in type.mro(cls)[1:]:
            m = getattr(base, "get_extra_output_methods", None)
            if m is not None:
                try:
                    methods += list(m())
                except TypeError:
                    try:
                        methods += list(m)
                    except Exception:
                        pass
        if "get_extra_pnginfo" not in methods:
            methods.append("get_extra_pnginfo")
        return list(dict.fromkeys(methods))

    def get_extra_pnginfo(self, **kwargs):
        """把本次调用的各输出值附上描述，写入保存文件元数据。"""
        extra = {}
        docs = type(self).OUTPUT_DOCS or {}
        for k, v in kwargs.items():
            if k in docs:
                extra[k] = {"description": docs[k]}
        return extra
