# -*- coding: utf-8 -*-
"""
Agnes 资产 JSON 拆分器
======================
两段式漫剧管线「工作流 A（前置定妆）」的核心节点：

把 AgnesAssetExtractor 输出的资产 JSON（角色/场景/道具/服装）
拆分为固定数量的「定妆提示词」+「保存前缀」，供下游
AgnesNovelTextToImage（生成定妆图）和 SaveImage（持久化）直接使用。

输出设计（每类最多 6 个资产，超出部分截断并在 json_ok 提示）：
  prefix_N   = "agnes_assets/characters_白奕"   -> SaveImage.filename_prefix
  prompt_N   = "Character concept sheet, 白奕, ..." -> TextToImage.prompt

空资产槽位输出空字符串（下游生成的图不带资产前缀，会被导出节点忽略，
建议在 ComfyUI 中右键 Mute 掉未使用的定妆节点以节省 API 额度）。
"""
import json
import re

from ._output_docs import OutputDocsMixin

DEFAULT_ASSET_DIR = "agnes_assets"


class AgnesAssetJsonSplitter(OutputDocsMixin):
    """将资产提取 JSON 拆分为定妆提示词 + 保存前缀"""

    DESCRIPTION = "把资产提取 JSON 拆成定妆图提示词+保存前缀（工作流A定妆区核心节点）"
    OUTPUT_DOCS = dict(
        (k, (
            f"资产 {k.split('_')[1]} 的保存前缀（如 agnes_assets/characters_白奕），连接 SaveImage.filename_prefix 使定妆图按资产自动命名"
            if k.startswith("prefix_")
            else f"资产 {k.split('_')[1]} 的定妆图英文提示词，连接 AgnesNovelTextToImage.prompt / AgnesAssetMaker.prompt；空字符串=该槽位无资产，可 Mute 下游节点"
        )) for k in [f"{p}_{i}" for i in range(1, 13) for p in ("prefix", "prompt")]
    )
    OUTPUT_DOCS["json_ok"] = "解析状态：ok=正常 / truncated=资产数超出截断 / empty=空 JSON / 具体错误信息"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "assets_json": ("STRING", {
                    "multiline": True,
                    "default": "[]",
                    "placeholder": "AgnesAssetExtractor 输出的 characters_json 等",
                    "tooltip": "资产提取节点输出的 JSON（characters/locations/props/costumes/weather）"
                }),
                "asset_type": (["characters", "locations", "props", "costumes", "weather"], {
                    "default": "characters",
                    "tooltip": "资产类型，决定提示词模板"
                }),
            },
            "optional": {
                "asset_dir": ("STRING", {
                    "default": DEFAULT_ASSET_DIR,
                    "tooltip": "定妆图保存目录（ComfyUI output 下）"
                }),
                "max_items": ("INT", {
                    "default": 6, "min": 1, "max": 12,
                    "tooltip": "最多拆分几个资产（决定定妆节点数量）"
                }),
            }
        }

    # 固定输出 12 组（每组 prefix + prompt），外加 json_ok 状态
    RETURN_TYPES = tuple(["STRING"] * 24) + ("STRING",)
    RETURN_NAMES = tuple(
        [n for i in range(1, 13) for n in (f"prefix_{i}", f"prompt_{i}")]
    ) + ("json_ok",)
    RETURN_LABELS = tuple(
        [n for i in range(1, 13) for n in (f"前缀{i}", f"提示词{i}")]
    ) + ("解析状态",)
    FUNCTION = "split"
    CATEGORY = "Agnes Novel"

    MAX_OUTPUTS = 12  # 最大拆分输出组数

    # 各类型提示词模板（英文，{name}/{desc} 占位）
    _TEMPLATES = {
        "characters": ("Character concept sheet, {name}, {desc}, full body, front view, "
                       "clean background, consistent character design, anime style, detailed face"),
        "locations": ("Location concept art, {name}, {desc}, wide angle, environment design, "
                      "clean composition, anime background style"),
        "props": ("Prop design, {name}, {desc}, isolated on clean background, "
                  "detailed object, anime style"),
        "costumes": ("Costume design sheet, {name}, {desc}, front view, clothing detail, "
                     "clean background, anime style"),
        "weather": ("Weather atmosphere concept, {name}, {desc}, cinematic sky, "
                    "atmospheric lighting, anime style"),
    }

    def split(self, assets_json, asset_type, asset_dir=DEFAULT_ASSET_DIR, max_items=6):
        # 解析 JSON -> 统一转为 [{name, desc}] 列表
        items = self._parse(assets_json, asset_type)
        ok = True
        if items is None:
            items = []
            ok = False

        outputs = []
        template = self._TEMPLATES.get(asset_type, "{name}, {desc}")
        max_items = max(1, min(int(max_items), self.MAX_OUTPUTS))
        for i in range(self.MAX_OUTPUTS):
            if i < len(items) and i < max_items:
                name, desc = items[i]
                prefix = f"{asset_dir}/{asset_type}_{name}"
                prompt = template.format(name=name, desc=desc)
            else:
                prefix, prompt = "", ""
            outputs.extend([prefix, prompt])

        status = ("✅ 解析成功" if ok else "⚠️ JSON 解析失败，请检查资产提取输出")
        if len(items) > max_items:
            status += f"（共{len(items)}个资产，仅拆分前{max_items}个）"
        outputs.append(status)
        return tuple(outputs)

    # ==========================================================
    # 内部解析
    # ==========================================================

    def _parse(self, assets_json, asset_type):
        """解析 JSON 为 [{name, desc}] 列表；失败返回 None"""
        try:
            data = json.loads(assets_json or "[]")
        except json.JSONDecodeError:
            return None

        if isinstance(data, dict):
            # 兼容 {"characters": [...]} 包装
            data = data.get(asset_type, [])
        if not isinstance(data, list):
            return None

        items = []
        for item in data:
            if isinstance(item, str):
                items.append((item.strip(), item.strip()))
            elif isinstance(item, dict):
                name = item.get("name") or item.get("character") or item.get("character_name")
                if not name:
                    continue
                # 汇总描述字段
                desc_parts = []
                for k in ("gender", "age", "appearance", "personality",
                          "description", "era", "environment"):
                    v = item.get(k)
                    if v:
                        desc_parts.append(str(v))
                desc = "，".join(desc_parts) if desc_parts else name
                # 服装：name 用 "角色_服装简称"，避免同名覆盖
                if asset_type == "costumes" and item.get("character"):
                    short = self._short_costume(desc)
                    name = f"{item['character']}_{short}"
                items.append((name, desc))
        return items

    @staticmethod
    def _short_costume(desc):
        """从服装描述提取简称（用于文件名）"""
        s = re.sub(r"[的、和与及着穿戴]", "", desc)
        s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)
        return s[:6] if s else "服装"


NODE_CLASS_MAPPINGS = {"AgnesAssetJsonSplitter": AgnesAssetJsonSplitter}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetJsonSplitter": "✂️ Agnes 资产拆分器"}
