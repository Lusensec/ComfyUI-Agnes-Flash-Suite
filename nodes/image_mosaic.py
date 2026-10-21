# -*- coding: utf-8 -*-
"""
Agnes 图像拼图节点
==================
把批量节点的 20 路 IMAGE 输出（Agnes 三视图批量生成 的 image_1..20）
汇聚成 1 路拼图，动态数量展示：

- 20 个图像输入槽，未连接的空槽自动跳过
- 全黑占位张量（批量节点跳过/失败槽的 512×512 黑图）自动过滤，不占用格子
- PIL 合成 2 列 × ⌈N/2⌉ 行网格：单元格等宽（以最大图宽为准，上限 1600px）、
  深灰背景 + 8px 间距、每格左上角标槽号
- 有效图数 N 决定网格行数（动态），全无效时回落 1 张 512×512 黑图占位
- 纯本地合成，不调 API；mosaic 可连 预览图像 / SaveImage 一次看全批/存全批

典型链路：
  Agnes 三视图批量生成.image_1..20 ─▶ Agnes 图像拼图 ─▶ 预览图像 / SaveImage
"""

import numpy as np
import torch

from ._output_docs import OutputDocsMixin


MAX_SLOTS = 20
CELLS = 2          # 网格列数
GAP = 8            # 间距（px）
BG = (30, 30, 30)  # 深灰底
CELL_CAP = 1600    # 单元格最大宽度（px，超出等比缩小）
BLACK_W = 512
BLACK_H = 512


def _black_placeholder():
    """全无效时的单张黑图占位（与批量节点占位同规格）"""
    return torch.zeros(1, BLACK_H, BLACK_W, 3)


class AgnesImageMosaic(OutputDocsMixin):
    """图像拼图：20 路图像合成 2 列网格，自动跳过空槽与全黑占位，N 动态定行数"""

    DESCRIPTION = "图像拼图：20 个图像输入（对应 三视图批量生成 等批量节点 image_1..20），合成 1 张 2 列网格拼图，自动跳过未连接槽与全黑占位图，有效图数 N 动态决定行数；全无效回落 1 张黑图占位；纯本地不调 API"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：mosaic（拼图张量）+ count（N/20）──
    RETURN_NAMES = ("mosaic", "count")
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_LABELS = ("拼图预览", "有效图数")
    OUTPUT_DOCS = {
        "mosaic": (
            "2 列 × ⌈N/2⌉ 行网格拼图（单元格等宽、深灰背景 + 8px 间距、每格标槽号）；"
            "自动跳过未连接槽与全黑占位；全无效=1 张 512×512 黑图占位；可连 预览图像 / SaveImage"
        ),
        "count": "有效图数「N/20」（未连接槽与全黑占位不计）",
    }

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for i in range(1, MAX_SLOTS + 1):
            required[f"image_{i}"] = ("IMAGE",)
        return {"required": required, "optional": {}}

    def generate(self,
                 image_1=None, image_2=None, image_3=None, image_4=None,
                 image_5=None, image_6=None, image_7=None, image_8=None,
                 image_9=None, image_10=None, image_11=None, image_12=None,
                 image_13=None, image_14=None, image_15=None, image_16=None,
                 image_17=None, image_18=None, image_19=None, image_20=None):
        from PIL import Image as PILImage, ImageDraw

        slots = [image_1, image_2, image_3, image_4, image_5,
                 image_6, image_7, image_8, image_9, image_10,
                 image_11, image_12, image_13, image_14, image_15,
                 image_16, image_17, image_18, image_19, image_20]

        # ── 过滤：未连接=None；全黑占位（全零张量）跳过 ──
        valid = []
        for i, img in enumerate(slots, 1):
            if img is None:
                continue
            t = img if img.dim() == 4 else img.unsqueeze(0)
            t = t[0]  # [H,W,3]，取首张
            if bool(t.ne(0).any()):  # 全零=批量节点黑图占位
                valid.append((i, t))

        if not valid:
            print(f"[Agnes 图像拼图] 无有效图（{MAX_SLOTS} 槽均未连接或全为黑图占位），返回 512 黑图占位")
            return _black_placeholder(), f"0/{MAX_SLOTS}"

        # ── 单元格等宽：以最大图宽为准（上限 CELL_CAP），等比缩高 ──
        target_w = min(max(int(t.shape[1]) for _, t in valid), CELL_CAP)
        cells = []
        for i, t in valid:
            # t: [H,W,3] float 0..1（ComfyUI IMAGE 约定）→ PIL RGB，无需 permute
            arr = (t.cpu().clamp(0.0, 1.0).numpy() * 255).astype("uint8")
            im = PILImage.fromarray(arr, "RGB")
            if im.width != target_w:
                h2 = max(1, round(im.height * target_w / im.width))
                im = im.resize((target_w, h2), PILImage.LANCZOS)
            cells.append((i, im))

        # ── 2 列网格：行高=该行最高格，格在行内垂直居中 ──
        rows = [cells[k:k + CELLS] for k in range(0, len(cells), CELLS)]
        row_hs = [max(im.height for _, im in row) for row in rows]
        canvas_w = CELLS * target_w + (CELLS + 1) * GAP
        canvas_h = sum(row_hs) + (len(rows) + 1) * GAP
        canvas = PILImage.new("RGB", (canvas_w, canvas_h), BG)
        draw = ImageDraw.Draw(canvas)
        y = GAP
        for row, rh in zip(rows, row_hs):
            x = GAP
            for idx in range(CELLS):
                if idx < len(row):
                    n, im = row[idx]
                    py = y + (rh - im.height) // 2
                    canvas.paste(im, (x, py))
                    draw.text((x + 4, py + 4), f"#{n}", fill=(255, 255, 255),
                              stroke_width=2, stroke=(0, 0, 0))
                x += target_w + GAP
            y += rh + GAP

        arr = np.frombuffer(canvas.tobytes(), dtype="uint8").reshape(
            canvas_h, canvas_w, 3,
        ).astype("float32") / 255.0
        mosaic = torch.from_numpy(arr).unsqueeze(0)  # [1,H,W,3]（ComfyUI IMAGE 约定）

        n = len(valid)
        print(f"[Agnes 图像拼图] 有效 {n}/{MAX_SLOTS} 张 → 拼图 {canvas_w}×{canvas_h}（{len(rows)} 行 × {CELLS} 列，槽位 {[i for i, _ in valid]}）")
        return mosaic, f"{n}/{MAX_SLOTS}"


NODE_CLASS_MAPPINGS = {"AgnesImageMosaic": AgnesImageMosaic}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesImageMosaic": "🧩 Agnes 图像拼图"}
