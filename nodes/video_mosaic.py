# -*- coding: utf-8 -*-
"""
Agnes 视频拼图节点（Agnes 图像拼图 的视频版，N 路视频 → 1 个矩阵视频）
================================================================
把「Agnes 视频任务批量收取」的 20 路 video_i 输出（或 all_video_paths 总输入
一根线 JSON 数组）同步拼成 columns × ⌈N/columns⌉ 矩阵视频（「分镜墙」，
一个节点/一个 Save Video 看全批 20 镜），自动保存 mp4 到
output/agnes_videos/（H.264，libx264 ultrafast；环境缺 libx264 回退 mpeg4）。

输入（与 图像拼图 同款语义，全部可选不连线不红框）：
  - all_video_paths 总输入（推荐一根线）：直连 批量收取 all_video_paths 输出
    （20 元素 JSON 数组；条目=本地落盘路径 / "" 空槽 / NO_VIDEO_ 黑帧占位
    路径（可解码，矩阵中显示为黑格）/ 服务端 URL（无法本地落盘，跳过并注记））；
    连上时优先用它（20 个 video_i 槽忽略，日志标注）；未连上走 20 槽
  - video_1..video_20：直连 批量收取 video_i（原生 VIDEO 类型）
  - columns 矩阵列数（默认 5）/ cell_width 单元格宽（0=自动）

拼接语义（对齐 图像拼图「N 动态定行数」）：
  - 有效视频数 N（可解码条目，空槽/URL 跳过）决定行数 ⌈N/columns⌉；
  - 播放同步：输出帧率=首个有效视频 fps（缺省 24），总时长=最长视频
    （短视频末帧冻结；无效槽不占格，有效格左上角标原槽号 #i）；
  - 全无效=回落 2 秒黑帧占位视频 + status 标注 error（队列不打断）

输出（3 档，同 文生视频/批量收取 环境动态类型）：
  原生 ComfyUI=VIDEO（VideoFromFile 惰性引用，节点面板内嵌播放，可再连
  Save Video 自定义前缀存档）/ VHS=VHS_VIDEOINFO / 无视频节点=本地路径字符串
  + count 有效视频数（N/分母）+ status 执行状态 JSON 文本

纯本地 PyAV（av）解码/编码，零 API 调用；内存占用=每路 1 帧 + 1 张画布。

典型链路（视频线·全批一眼验收，20 镜/波）：
  Agnes 视频任务批量收取（video_1..20 + all_video_paths）
  → all_video_paths 一根线直连 Agnes 视频拼图（all_video_paths）
  → mosaic_video 矩阵视频（节点面板内嵌播放；可再连 Save Video 存档）
"""

import io
import json
import math
import os
import time
from typing import Tuple

from ._output_docs import OutputDocsMixin
from .text2video import _VIDEO_MODE, _VIDEO_OUTPUT_TYPE, _make_result
from .video_task_collect import _VHS_EMPTY, _get_output_dir, _make_placeholder_video

MAX_SLOTS = 20
DEFAULT_COLUMNS = 5
DEFAULT_FPS = 24
GAP = 8            # 网格间距（px，同 图像拼图）
BG = (30, 30, 30)  # 深灰底（同 图像拼图）
CELL_MIN = 160     # 自动单元格宽下限（px）
CELL_MAX = 1280    # 单元格宽上限（px）


def _parse_all_paths(raw) -> Tuple[list, list, int]:
    """解析 all_video_paths 总输入：20 元素保位路径 JSON 数组（直连 批量收取
    all_video_paths 输出）。条目形态：本地落盘路径 / "" 空槽 / 服务端 URL
    （无法本地解码，跳过并注记）。返回 (slots(20 槽保位列表), 注记列表, 原始条目数)。"""
    raw = str(raw or "").strip()
    notes = []
    if raw:
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            obj = [raw]
        if isinstance(obj, str):
            obj = [obj]
        if not isinstance(obj, list):
            obj = [str(obj)]
        for el in obj:
            if str(el or "").strip().startswith(("http://", "https://")):
                notes.append("服务端 URL 条目（下载失败未落盘，矩阵中为黑格）")
    else:
        obj = []
    raw_n = len(obj)
    slots = []
    for el in obj:
        p = str(el or "").strip()
        if p.startswith(("http://", "https://")):
            p = ""
        slots.append(p)
    slots = slots + [""] * (MAX_SLOTS - len(slots))
    return slots[:MAX_SLOTS], notes[:5], raw_n


def _slot_source(v):
    """video_i 槽取值 → 可解码源：路径字符串 / av 可 open 的文件对象；
    None=未连接；帧分量型 VIDEO（CreateVideo 等）无文件源，返回 None。"""
    if v is None:
        return None
    if isinstance(v, str):
        p = v.strip()
        return p or None
    getter = getattr(v, "get_stream_source", None)
    if callable(getter):
        try:
            src = getter()
        except Exception:
            return None
        if isinstance(src, (str, io.BytesIO)):
            return src
    return None


def _slot_font(size):
    """槽号标签字体：优先系统 truetype（Windows arial / Linux DejaVu），缺失回退位图默认。"""
    from PIL import ImageFont
    for name in ("arial.ttf", "DejaVuSans.ttf", "liberation_sans-regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


class AgnesVideoMosaic(OutputDocsMixin):
    """Agnes 视频拼图：N 路视频（all_video_paths 总输入优先 / 20 个 video_i 槽）同步拼成 columns×⌈N/columns⌉ 矩阵视频，自动落盘 mp4；全无效回落黑帧占位。"""

    DESCRIPTION = "视频拼图（图像拼图 的视频版，纯本地零 API）：all_video_paths 总输入（直连 批量收取 all_video_paths 输出，一根线）优先，或 20 个 video_i 槽（直连 批量收取 video_i，原生 VIDEO）；把 N 个可解码视频同步拼成 columns × ⌈N/columns⌉ 矩阵视频（输出帧率=首个有效视频 fps，总时长=最长视频，短视频末帧冻结，无效槽不占格，格左上角标原槽号 #i；深灰底 + 8px 间距，布局语义同 图像拼图）；H.264 自动保存到 output/agnes_videos/（节点面板内嵌播放；可再连 Save Video 自定义前缀存档）；全无效=2 秒黑帧占位 + status 标注 error（队列不打断）；输出 3 路：mosaic_video（环境动态类型 VIDEO/VHS_VIDEOINFO/路径字符串）+ count（N/分母）+ status（执行状态：ok 落盘路径与规格 / error 原因）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    RETURN_NAMES = ("mosaic_video", "count", "status")
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING", "STRING")
    RETURN_LABELS = ("矩阵视频", "有效视频数", "执行状态")
    OUTPUT_DOCS = {
        "mosaic_video": (
            "columns × ⌈N/columns⌉ 矩阵视频（H.264 mp4，自动落盘 output/agnes_videos/；播放同步：短视频末帧冻结，"
            "无效槽不占格，格左上角标原槽号）；类型随环境：原生 ComfyUI=VIDEO（节点面板内嵌播放，可连 Save Video 再存档）"
            "/ VHS=VHS_VIDEOINFO / 无视频节点=本地路径字符串；全无效=2 秒黑帧占位（status 带 error 内容，队列不打断）"
        ),
        "count": "有效视频数「N/分母」（分母=20 槽模式为 20、all_video_paths 总输入模式为其条目数；空槽/URL 条目/解码失败不计）",
        "status": "执行状态：ok: 有效 N/M → 矩阵 C×R（WxH@fps 秒）已保存 <路径>；error: 原因（无有效输入→黑帧占位 / 逐槽解码失败清单）",
    }

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            "all_video_paths": ("STRING", {
                "label": "全部视频路径（JSON 总输入）",
                "multiline": True,
                "default": "",
                "placeholder": '["…/output/agnes_videos/a.mp4", "…/b.mp4", ""]\n直连 Agnes 视频任务批量收取 的 all_video_paths 输出（20 元素路径 JSON 数组）',
                "tooltip": "总输入（优先）：直连 Agnes 视频任务批量收取 的 all_video_paths 输出（20 元素 JSON 数组，一行带齐全批路径）；条目=本地落盘路径（NO_VIDEO_ 黑帧占位也可解码，显示为黑格）/ 空槽跳过 / 服务端 URL 跳过并注记；连上时优先（20 个 video_i 槽忽略，日志标注），未连上走 20 槽（旧接法兼容）",
            }),
        }
        for i in range(1, MAX_SLOTS + 1):
            optional[f"video_{i}"] = ("VIDEO", {
                "tooltip": f"第 {i} 个视频槽（可选，不连线=该槽自动跳过不红）：直连 Agnes 视频任务批量收取 的 video_i（原生 VIDEO）；all_video_paths 总输入连上时本组槽忽略",
            })
        return {
            "required": {
                "columns": ("INT", {
                    "label": "矩阵列数",
                    "default": DEFAULT_COLUMNS,
                    "min": 1,
                    "max": 6,
                    "step": 1,
                    "tooltip": "矩阵列数（行数=⌈有效视频数/列数⌉，同 图像拼图 动态定行数）：默认 5（20 镜=4 行）；1=纵向长条（逐镜播放式）",
                }),
                "cell_width": ("INT", {
                    "label": "单元格宽（px）",
                    "default": 0,
                    "min": 0,
                    "max": 1280,
                    "step": 16,
                    "tooltip": "单元格宽（px）：0=自动（源最大宽÷列数，下限 160 上限 1280；20 镜 720P 16:9 默认列 5 ≈256）；固定值=所有格等宽等比缩高",
                }),
            },
            "optional": optional,
        }

    # ── PyAV 解码/重采样 ──
    @staticmethod
    def _probe(source):
        """探测源视频 fps_in / 宽高 / 时长 / 源帧数（容器即读即关，防句柄泄漏）。"""
        import av
        c = av.open(source)
        try:
            vs = next((s for s in c.streams if s.type == "video"), None)
            if vs is None:
                raise ValueError("无视频流")
            fps_in = float(vs.average_rate) if vs.average_rate else float(DEFAULT_FPS)
            if not math.isfinite(fps_in) or fps_in <= 0:
                fps_in = float(DEFAULT_FPS)
            dur = None
            if c.duration:
                dur = float(c.duration) / av.time_base
            if dur is None and vs.duration and vs.time_base:
                dur = float(vs.duration) * float(vs.time_base)
            return {"fps_in": fps_in, "width": vs.width, "height": vs.height,
                    "n_src": int(vs.frames or 0), "dur": dur}
        finally:
            c.close()

    @staticmethod
    def _frames_iter(source):
        """解码器生成器：逐帧产出 RGB uint8 数组（H,W,3）；耗尽后冻结由调用方处理。"""
        import av
        c = av.open(source)

        def _gen():
            try:
                for fr in c.decode(video=0):
                    yield fr.to_ndarray(format="rgb24")
            finally:
                c.close()

        return _gen()

    def generate(self,
                 all_video_paths: str = "",
                 video_1=None, video_2=None, video_3=None, video_4=None, video_5=None,
                 video_6=None, video_7=None, video_8=None, video_9=None, video_10=None,
                 video_11=None, video_12=None, video_13=None, video_14=None, video_15=None,
                 video_16=None, video_17=None, video_18=None, video_19=None, video_20=None,
                 columns: int = DEFAULT_COLUMNS, cell_width: int = 0) -> Tuple:
        import numpy as np
        import av
        from PIL import Image as PILImage, ImageDraw

        # ── 数据源优先级：all_video_paths 总输入（JSON 路径数组）→ 20 槽（旧接法）──
        slot_values = [video_1, video_2, video_3, video_4, video_5,
                       video_6, video_7, video_8, video_9, video_10,
                       video_11, video_12, video_13, video_14, video_15,
                       video_16, video_17, video_18, video_19, video_20]
        merged = str(all_video_paths or "").strip()
        notes = []
        if merged:
            slots, url_notes, raw_n = _parse_all_paths(merged)
            notes.extend(url_notes)
            n_individual = sum(1 for v in slot_values if _slot_source(v) is not None)
            if n_individual:
                notes.append(f"video_1..{MAX_SLOTS} 逐一连线 {n_individual} 槽与总输入并存，按置顶优先语义总输入生效")
            sources = [(i, (p if p else None)) for i, p in enumerate(slots, 1) if p]
            total = raw_n
            source = f"all_video_paths 总输入（{raw_n} 条）"
        else:
            sources = [(i, _slot_source(v)) for i, v in enumerate(slot_values, 1) if _slot_source(v)]
            total = MAX_SLOTS
            source = f"video_1..{MAX_SLOTS} 槽"

        # ── 全无效 → 黑帧占位 + status 标注（队列不打断，同 批量收取 0 标记族语义）──
        if not sources:
            print(f"[Agnes 视频拼图] [跳过] 无有效视频输入（{source} 全空/全 URL）→ 2 秒黑帧占位，零解码")
            return self._result(_make_placeholder_video("empty", _get_output_dir()),
                                "0/%d" % total, "error: 无有效视频输入（all_video_paths 空且 video_1..20 全未连接，或条目全为服务端 URL）→ 黑帧占位")

        # ── 探测 + 源准备（失败的槽→黑格，status 附原因）──
        cols = max(1, min(int(columns or DEFAULT_COLUMNS), 6))
        items = []  # (slot_no, gen, fps_in, width, height, n_out)
        dom_w, dom_h, fps_out = None, None, None
        failed = []
        for i, src in sources:
            try:
                meta = self._probe(src)
            except Exception as e:
                failed.append(f"#{i} 解码失败: {str(e)[:80]}")
                items.append((i, None, None, None, None, 0))
                continue
            if fps_out is None:
                fps_out = min(max(meta["fps_in"], 1.0), 60.0)
            # 重采样到 fps_out 后的输出帧数（时长已知=按时长；否则按源帧数换算）
            if meta["dur"]:
                n_out = int(round(meta["dur"] * fps_out))
            elif meta["n_src"]:
                n_out = int(round(meta["n_src"] * fps_out / meta["fps_in"]))
            else:
                n_out = 0
            try:
                gen = self._frames_iter(src)
            except Exception as e:
                failed.append(f"#{i} 解码失败: {str(e)[:80]}")
                items.append((i, None, None, None, None, 0))
                continue
            items.append((i, gen, meta["fps_in"], meta["width"], meta["height"], n_out))
            if dom_w is None and meta["width"]:
                dom_w, dom_h = meta["width"], meta["height"]

        valid = [it for it in items if it[1] is not None]
        if not valid:
            print(f"[Agnes 视频拼图] [错误] 全部 {len(items)} 条解码失败（{'; '.join(failed[:5])}）→ 2 秒黑帧占位")
            return self._result(_make_placeholder_video("error", _get_output_dir()),
                                "0/%d" % total, "error: 全部条目解码失败：" + "；".join(failed[:5]))
        if fps_out is None:
            fps_out = float(DEFAULT_FPS)
        if dom_w is None:
            dom_w, dom_h = 1280, 720

        # ── 网格几何（同 图像拼图：cells×rows + 深灰底 + 间距；H.264 需偶数）──
        n_valid = len(valid)
        rows = math.ceil(n_valid / cols)
        auto_w = max(CELL_MIN, min(CELL_MAX, max(dom_w, 160) // cols))
        cw = int(cell_width) if int(cell_width) > 0 else auto_w
        ch = max(2, int(round(cw * dom_h / max(dom_w, 1))))
        cw, ch = (cw // 2) * 2, (ch // 2) * 2
        W = (cols * cw + (cols + 1) * GAP) // 2 * 2
        H = (rows * ch + (rows + 1) * GAP) // 2 * 2
        n_total = max((it[5] for it in valid if it[5] > 0), default=1)

        # 静态标签叠层（#i 白字黑描边预烘焙一次，逐帧只做一次 alpha 合成）
        label_overlay = np.zeros((H, W, 4), dtype=np.uint8)
        for k, it in enumerate(valid):
            slot_no = it[0]
            r, cidx = divmod(k, cols)
            x0, y0 = GAP + cidx * (cw + GAP), GAP + r * (ch + GAP)
            patch = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
            d = ImageDraw.Draw(patch)
            fsize = max(14, min(40, cw // 16))  # 字号随格宽自适应
            d.text((4, 4), f"#{slot_no}", font=_slot_font(fsize), fill=(255, 255, 255, 255),
                   stroke_width=2, stroke=(0, 0, 0, 255))
            lab = np.asarray(patch, dtype=np.uint8)
            cell = label_overlay[y0:y0 + ch, x0:x0 + cw]
            a = lab[:, :, 3]
            m = a > 0
            cell[m, :3] = lab[m, :3]
            cell[m, 3] = np.maximum(cell[m, 3], a[m])

        # 各源解码器游标（按输出时间 t 惰性解码到 target 帧；耗尽=末帧冻结）
        item_by_slot = {it[0]: it for it in valid}
        cursors = {slot: {"idx": 0, "last": None} for slot in item_by_slot}

        def _advance(slot_no, t):
            it = item_by_slot[slot_no]
            st = cursors[slot_no]
            target = int(round(t * it[2] / fps_out))
            while st["idx"] < target:
                try:
                    st["last"] = next(it[1])
                    st["idx"] += 1
                except StopIteration:
                    break
            return st["last"]

        # ── 逐帧合成 + H.264 编码（ultrafast；缺 libx264 回退 mpeg4）──
        out_dir = _get_output_dir()
        out_path = os.path.join(out_dir, f"agnes_mosaic_{int(time.time())}.mp4")
        container = av.open(out_path, mode="w")
        codec_name, codec_note = "libx264", ""
        try:
            stream = container.add_stream(codec_name, rate=int(round(fps_out)))
        except Exception:
            codec_name, codec_note = "mpeg4", "（环境缺 libx264，回退 mpeg4）"
            stream = container.add_stream(codec_name, rate=int(round(fps_out)))
        stream.width, stream.height, stream.pix_fmt = W, H, "yuv420p"
        stream.options = {"preset": "ultrafast"}

        blank = np.zeros((ch, cw, 3), dtype=np.uint8)
        arr = np.zeros((H, W, 3), dtype=np.uint8)
        label_m = label_overlay[:, :, 3] > 0
        label_rgb = label_overlay[:, :, :3]
        print(f"\n[Agnes 视频拼图] 开始：有效 {n_valid}/{total}（{source}）→ 矩阵 {cols} 列 × {rows} 行"
              f"（{W}×{H}@{int(round(fps_out))}fps，{n_total} 帧 ≈{n_total / max(fps_out, 1):.1f}s）"
              f"，同步起播（短视频末帧冻结）")
        for t in range(n_total):
            arr[:] = BG
            for k, it in enumerate(valid):
                slot_no = it[0]
                r, cidx = divmod(k, cols)
                frame = _advance(slot_no, t)
                x0, y0 = GAP + cidx * (cw + GAP), GAP + r * (ch + GAP)
                if frame is None:
                    arr[y0:y0 + ch, x0:x0 + cw] = blank
                    continue
                # 等比缩放居中（不同宽高比源不拉伸）
                f_h, f_w = frame.shape[:2]
                scale = min(cw / max(f_w, 1), ch / max(f_h, 1))
                nw = max(2, int(f_w * scale) // 2 * 2)
                nh = max(2, int(f_h * scale) // 2 * 2)
                if (nw, nh) != (f_w, f_h):
                    frame = np.asarray(
                        PILImage.fromarray(frame, "RGB").resize((nw, nh), PILImage.LANCZOS),
                        dtype=np.uint8)
                ox = x0 + (cw - nw) // 2
                oy = y0 + (ch - nh) // 2
                arr[oy:oy + nh, ox:ox + nw] = frame
            arr[label_m] = label_rgb[label_m]
            vf = av.VideoFrame.from_ndarray(arr, format="rgb24")
            vf.pts = t
            for pkt in stream.encode(vf):
                container.mux(pkt)
        for pkt in stream.encode(None):
            container.mux(pkt)
        container.close()

        status = (f"ok: 有效 {n_valid}/{total} → 矩阵 {cols}×{rows}（{W}×{H}@{int(round(fps_out))}fps）"
                  f"已保存 {out_path}{codec_note}"
                  + (f"；解码失败槽：{'；'.join(failed)}" if failed else "")
                  + (f"；注记：{'；'.join(notes)}" if notes else ""))
        print(f"[Agnes 视频拼图] 完成：{status}")
        return self._result(out_path, f"{n_valid}/{total}", status)

    def _result(self, path: str, count: str, status: str) -> Tuple:
        """按环境三档构造 (video, count, status)（同 批量收取 _video_for 约定）。"""
        from .text2video import _VIDEO_MODE as _m
        if _m == "comfy_api":
            video = _make_result(path, "")[0]
        elif _m == "vhs":
            video = _VHS_EMPTY if "NO_VIDEO_" in os.path.basename(path) else {
                "filename": os.path.basename(path), "subfolder": "agnes_videos", "type": "output"}
        else:
            video = path
        return (video, count, status)


NODE_CLASS_MAPPINGS = {"AgnesVideoMosaic": AgnesVideoMosaic}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoMosaic": "🧩 Agnes 视频拼图"}
