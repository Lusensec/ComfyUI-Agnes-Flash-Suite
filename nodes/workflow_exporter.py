# -*- coding: utf-8 -*-
"""
Agnes 工作流 B 导出节点
========================
两段式漫剧管线中的「衔接节点」：

工作流 A（前置定妆）运行后，本节点读取：
  1. 场景→资产映射表（AgnesNovelLLMChat 输出的 JSON）
  2. 定妆图清单（assets_index.json，含已生成的定妆图路径）

然后自动生成「工作流 B（漫剧创作）」的完整 JSON 文件，
用户新建页面 Load 该文件即可直接跑漫剧创作。

用法（工作流 A 内）:
  场景映射 JSON ──→ AgnesWorkflowExporter.asset_map_json
  ──→ 输出 workflow_b.json 到 ComfyUI output/ 目录
"""
import json
import os
import re
import time

import folder_paths

from ..api import get_api_key, BASE_URL, CHAT_MODEL

# 定妆图默认目录（ComfyUI output 下）
DEFAULT_ASSET_DIR = "agnes_assets"


class AgnesWorkflowExporter:
    """将前置定妆结果导出为「漫剧创作工作流 B」的 JSON"""

    DESCRIPTION = "读取场景映射+定妆图清单，导出工作流 B 的 JSON 文件（两段式管线的衔接节点）"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_map_json": ("STRING", {
                    "multiline": True,
                    "default": "{}",
                    "placeholder": '{"scene_1": ["白奕","教室"], ...}',
                    "tooltip": "场景→资产映射 JSON（从 AgnesNovelLLMChat 输出获取）"
                }),
            },
            "optional": {
                "asset_dir": ("STRING", {
                    "default": DEFAULT_ASSET_DIR,
                    "tooltip": "定妆图目录（ComfyUI output 下）"
                }),
                "output_filename": ("STRING", {
                    "default": "workflow_b.json",
                    "tooltip": "输出的工作流 B 文件名"
                }),
                "images_ready": ("IMAGE", {
                    "tooltip": "连接任一（最好是最后一个）定妆图的 images 输出，确保导出在定妆图生成后执行"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING",)
    RETURN_NAMES = ("workflow_b_path", "status",)
    RETURN_LABELS = ("工作流B路径", "状态")
    FUNCTION = "export"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    # 等待定妆图落盘的轮询参数（防止 SaveImage 未写完就扫描）
    WAIT_TIMEOUT = 60      # 最多等待秒数
    WAIT_INTERVAL = 2      # 轮询间隔秒数

    # ---- 节点 widget 配置（用户可调） ----
    # strength: 图生图参考强度
    # quality / aspect_ratio: 生成默认
    STRENGTH = 0.55
    QUALITY = "2K"
    ASPECT_RATIO = "16:9"
    # Jimeng 图生图模型（与已验证的 workflow-manju-b-video.json 保持一致）
    IMAGE_MODEL = "jimeng-image-5.0-lite"
    # Agnes 视频模型：新 2.5 Flash（4-12s / 720P，支持首尾帧与参考图）
    VIDEO_MODEL = "agnes-video-2.5-flash"
    # Jimeng 图生图配置
    API_KEY = ""  # jimeng-free-api Authorization Bearer，用户填写
    DEFAULT_BASE_URL = "http://127.0.0.1:8001"

    # 参考图槽位分配优先级：角色 > 场景 > 道具 > 服装
    _TYPE_PRIORITY = {"characters": 0, "locations": 1, "props": 2,
                      "costumes": 3, "weather": 4}

    def export(self, asset_map_json, asset_dir=DEFAULT_ASSET_DIR,
               output_filename="workflow_b.json", images_ready=None):
        # ---------- 1. 解析输入 ----------
        try:
            asset_map = json.loads(asset_map_json or "{}")
        except json.JSONDecodeError as e:
            return ("", f"[Error] asset_map_json 不是有效 JSON: {e}")

        # ---------- 2. 扫描定妆图（带轮询等待） ----------
        output_dir = folder_paths.get_output_directory()
        asset_path = os.path.join(output_dir, asset_dir)
        assets = self._scan_assets(asset_path)  # {名称: 相对路径}

        # 若还没有定妆图，等待上游 SaveImage 落盘（最多 WAIT_TIMEOUT 秒）
        waited = 0
        while not assets and waited < self.WAIT_TIMEOUT:
            time.sleep(self.WAIT_INTERVAL)
            waited += self.WAIT_INTERVAL
            assets = self._scan_assets(asset_path)

        # ---------- 3. 生成工作流 B JSON ----------
        wf = self._build_workflow_b(asset_map, assets)
        out_path = os.path.join(output_dir, output_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(wf, f, indent=2, ensure_ascii=False)

        summary = (f"✅ 工作流B已导出: {out_path}\n"
                   f"   场景数: {len(asset_map)}\n"
                   f"   定妆图: {len(assets)} 张\n"
                   f"   节点数: {len(wf['nodes'])}, 连线数: {len(wf['links'])}\n"
                   f"   请新建页面 → Load 此文件 → Queue")
        return (out_path, summary)

    # ==========================================================
    # 内部工具
    # ==========================================================

    # SaveImage 生成的文件名形如: characters_白奕_20260818_220000_00001_.png
    # 需要去掉类型前缀 + 时间戳序号，还原资产名 "白奕"
    _TS_RE = re.compile(r"_\d{8}_\d{6}_\d+_?$")
    _TYPE_PREFIXES = ("characters_", "locations_", "props_", "costumes_", "weather_")

    def _scan_assets(self, asset_path):
        """扫描定妆图目录，返回 {资产名(去后缀): 相对路径}"""
        assets = {}
        if not os.path.isdir(asset_path):
            return assets
        for fname in os.listdir(asset_path):
            if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            # 只认带类型前缀的定妆图（空槽位占位图/其他文件直接忽略）
            if not fname.startswith(self._TYPE_PREFIXES):
                continue
            name = os.path.splitext(fname)[0]
            # 去掉 "characters_" 等类型前缀，保留资产名
            short = name.split("_", 1)[1]
            # 去掉 SaveImage 追加的时间戳序号
            short = self._TS_RE.sub("", short)
            short = short.strip("_ ")
            if not short:
                continue
            assets[short] = os.path.join(os.path.basename(asset_path), fname)
        return assets

    def _build_workflow_b(self, asset_map, assets):
        """构造工作流 B 的 workflow dict"""
        wf = {
            "last_node_id": 0, "last_link_id": 0,
            "nodes": [], "links": [], "groups": [],
            "config": {"workflow_name": "Agnes 漫剧创作 (工作流B)",
                       "source": "AgnesWorkflowExporter"},
            "extra": {"ds": {"scale": 1.0, "offset": [0, 0]}},
            "version": 0.4,
        }
        next_nid = 1

        def add_node(ntype, pos, size, inputs, outputs, widgets_vals, props=None):
            nonlocal next_nid
            nid = next_nid
            next_nid += 1
            wf["last_node_id"] = nid
            node = {
                "id": nid, "type": ntype, "pos": list(pos), "size": list(size),
                "flags": {}, "order": 0, "mode": 0,
                "inputs": inputs, "outputs": outputs,
                "properties": props or {"Node name for S&R": ntype},
                "widgets_values": widgets_vals,
            }
            wf["nodes"].append(node)
            return nid

        def add_link(from_id, from_slot, to_id, to_slot, typ="STRING"):
            wf["last_link_id"] += 1
            lid = wf["last_link_id"]
            wf["links"].append([lid, from_id, from_slot, to_id, to_slot, typ])
            return lid

        # ---- ① 定妆图 LoadImage 节点 ----
        load_ids = {}  # 资产名 -> node_id
        x = 60
        for name, rel_path in sorted(assets.items()):
            nid = add_node("LoadImage", (x, 60), (300, 120),
                [{"name": "image", "type": "STRING", "link": None}],
                [{"name": "IMAGE", "type": "IMAGE", "links": []},
                 {"name": "MASK", "type": "MASK", "links": None}],
                [rel_path])
            load_ids[name] = nid
            x += 320

        # ---- ② 场景文本输入 ----
        text_nid = add_node("PrimitiveStringMultiline", (60, 220), (420, 120),
            [], [{"name": "STRING", "type": "STRING", "links": []}],
            ["请输入场景文本（可从工作流A的场景切分输出复制，或用场景映射逐个生成）", True])

        # ---- ③ 场景图生图 + 视频链路 ----
        # 每场景: 图生图(主图=角色1 + 参考图) -> 图生视频 -> SaveVideo
        scene_ids = sorted(asset_map.keys(), key=lambda s: self._scene_num(s))
        col_x = 560
        for idx, scene_key in enumerate(scene_ids):
            base_x = col_x + (idx % 5) * 700
            base_y = 60 + (idx // 5) * 240
            scene_assets = asset_map.get(scene_key, [])

            # 图生图（Jimeng，单参考图）
            img2img_id = add_node("JimengImageToImage", (base_x, base_y), (380, 220),
                [{"name": "image", "type": "IMAGE", "link": None},
                 {"name": "prompt", "type": "STRING", "link": None},
                 {"name": "api_key", "type": "STRING", "link": None},
                 {"name": "base_url", "type": "STRING", "link": None},
                 {"name": "model", "type": "STRING", "link": None},
                 {"name": "ratio", "type": "STRING", "link": None},
                 {"name": "resolution", "type": "STRING", "link": None},
                 {"name": "sample_strength", "type": "FLOAT", "link": None},
                 {"name": "negative_prompt", "type": "STRING", "link": None}],
                [{"name": "images", "type": "IMAGE", "links": []},
                 {"name": "status", "type": "STRING", "links": None}],
                [scene_key, "", self.API_KEY or "", DEFAULT_BASE_URL,
                 self.IMAGE_MODEL, self.ASPECT_RATIO, self.QUALITY,
                 self.STRENGTH, ""])

            # 场景 prompt（用场景文本输入）
            l_text = add_link(text_nid, 0, img2img_id, 2)

            # 主图（第一个资产作为参考图，JimengImageToImage 支持单参考图）
            ordered = self._order_scene_assets(scene_assets, assets)
            for ai, asset_name in enumerate(ordered[:1]):
                target_id = load_ids.get(asset_name)
                if target_id is None:
                    continue
                add_link(target_id, 0, img2img_id, 0)   # 主图→image输入

            # 视频
            video_id = add_node("AgnesNovelImageToVideo", (base_x + 380, base_y), (380, 160),
                [{"name": "api_key", "type": "STRING", "link": None},
                 {"name": "image", "type": "IMAGE", "link": None},
                 {"name": "prompt", "type": "STRING", "link": None},
                 {"name": "model", "type": "STRING", "link": None},
                 {"name": "quality", "type": "STRING", "link": None},
                 {"name": "aspect_ratio", "type": "STRING", "link": None},
                 {"name": "num_frames", "type": "INT", "link": None},
                 {"name": "frame_rate", "type": "INT", "link": None},
                 {"name": "seed", "type": "INT", "link": None},
                 {"name": "max_wait_seconds", "type": "INT", "link": None}],
                [{"name": "video", "type": "VIDEO", "links": []},
                 {"name": "resolution", "type": "STRING", "links": None}],
                ["", "Smooth camera pan, subtle character motion, cinematic lighting",
                 self.VIDEO_MODEL, self.QUALITY, self.ASPECT_RATIO, 121, 24, 0, 600])

            # 保存
            save_id = add_node("SaveVideo", (base_x + 780, base_y), (280, 100),
                [{"name": "video", "type": "VIDEO", "link": None},
                 {"name": "filename_prefix", "type": "STRING", "link": None},
                 {"name": "format", "type": "COMBO", "link": None},
                 {"name": "codec", "type": "COMBO", "link": None}],
                [], [f"agnes_videos/{scene_key}", "auto", "auto"])

            # 连线: 图->视频, 视频->保存
            l_img_vid = add_link(img2img_id, 0, video_id, 1)
            l_vid_save = add_link(video_id, 0, save_id, 0)

        # ---------- 收尾: 补齐 outputs links ----------
        for n in wf["nodes"]:
            nid = n["id"]
            out_links = [l[0] for l in wf["links"] if l[1] == nid and l[2] == 0]
            if n["type"] in ("LoadImage", "JimengImageToImage",
                             "AgnesNovelImageToVideo", "PrimitiveStringMultiline"):
                if n["outputs"]:
                    n["outputs"][0]["links"] = out_links
            for inp in n.get("inputs", []):
                for l in wf["links"]:
                    if l[3] == nid and l[4] == n["inputs"].index(inp):
                        inp["link"] = l[0]

        return wf

    @staticmethod
    def _scene_num(scene_key):
        """从 scene_3 / scene_12 提取数字用于排序"""
        try:
            return int(str(scene_key).split("_")[-1])
        except (ValueError, IndexError):
            return 0

    def _asset_type(self, rel_path):
        """从定妆图相对路径推断资产类型前缀（characters/locations/...）"""
        base = os.path.basename(rel_path).replace("\\", "/")
        prefix = base.split("_", 1)[0] if "_" in base else ""
        return prefix if prefix in self._TYPE_PRIORITY else "other"

    def _order_scene_assets(self, scene_assets, assets):
        """按类型优先级排序场景资产：
        有定妆图的排前面（角色→场景→道具→服装），无定妆图的排最后（会被跳过）。
        保证主图尽量分配给角色，避免"教室当主图"的错位。"""
        def sort_key(name):
            if name in assets:
                return (0, self._TYPE_PRIORITY.get(self._asset_type(assets[name]), 9))
            return (1, 99)  # 无定妆图（降级资产）排最后
        return sorted(scene_assets, key=sort_key)


NODE_CLASS_MAPPINGS = {"AgnesWorkflowExporter": AgnesWorkflowExporter}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesWorkflowExporter": "📤 Agnes 工作流B导出"}
