# -*- coding: utf-8 -*-
"""
OutputDocsMixin：节点输出描述共享 Mixin
========================================
ComfyUI 节点规格中，输入参数（widgets）有 tooltip/label 描述机制，
而输出（RETURN_*）只有短标签（RETURN_NAMES/RETURN_LABELS），没有长描述字段。
本 mixin 通过 ComfyUI 官方扩展点 get_extra_output_methods / get_extra_pnginfo
为每个节点补上"输出描述"：保存图像/视频（或连接支持 pnginfo 的节点）时，
会把类属性 OUTPUT_DOCS 中的各输出说明写入文件元数据，便于在
ComfyUI 画廊、PNG info 查看器中理解每个输出的含义与去向。

用法：
    class MyNode(OutputDocsMixin):
        OUTPUT_DOCS = {
            "script": "生成的完整解说文案（连接 SaveText 或直接复制使用）",
            ...
        }
"""


class OutputDocsMixin:
    """为节点提供统一的输出描述机制（写入 pnginfo 元数据）。"""

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
