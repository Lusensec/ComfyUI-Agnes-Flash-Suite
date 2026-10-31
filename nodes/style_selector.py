"""
Agnes 创作风格配置节点
=====================
漫剧/短视频全局创作基调节点（纯本地组合，不调用 API、无需 API Key）。
旧名「Agnes 风格选择」，改名不改类名（AgnesStyleSelector），旧实例零影响。

定位：全画布唯一的"创意基调"配置点，与「Agnes API Key 配置」（工程通道层）
并列——一个管"拍成什么样"，一个管"怎么调服务"。参数命名与值域与下游
消费方一一对应（同语义=同名+同值域，连线点标签直接写目的地）：

  轴（输入）              值域                        下游对应
  ─ visual_style 视觉风格  10 画风                    文本注入（style_block）
  ─ tag 题材/导演基调      15 题材名                  Agnes 剧本生成·tag（同名直连）
  ─ rhythm 节奏           快/中/慢 3 值               Agnes 剧本生成·rhythm（同值域可连）
  ─ emotion 情绪基调       爽/暖/爆笑/热血/紧张/泪     Agnes 剧本生成·emotion（同值域可连）
  ─ aspect 画幅基调        16:9/9:16/1:1              建议值进风格块（API 参数归节点自持）
  ─ extra 自由补充         任意一句话                  进风格块

输出 7 路：
  style_block      风格说明块（文本注入：接 剧本生成·风格规范块 槽 / 任意 LLM 提示词输入）
  visual_style_out 视觉风格名
  tag_out          题材 tag 名（直连 剧本生成·tag）
  rhythm_out       节奏（直连 剧本生成·rhythm）
  emotion_out      情绪基调（直连 剧本生成·emotion）
  aspect_out       画幅（建议值）
  style_json       机器可读 JSON（visual/tag/extra/rhythm/emotion/aspect）
"""

import json
from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesStyleSelector(OutputDocsMixin):
    """Agnes 创作风格配置节点（创意基调：视觉风格 × 题材 × 节奏 × 情绪 × 画幅，纯本地组合，不调用 API）。"""

    CATEGORY = "Agnes Novel"

    VISUAL_DESC = {
        "国风3D": "国风3D：东方美学三维渲染，鎏金祥云纹样，丝绸流动感，仙侠/国风场景质感，柔和电影级光影",
        "二次元2D": "日系二次元：赛璐璐风格2D动画，大眼清晰线稿，色彩鲜亮，明暗对比明快",
        "国漫手绘": "国漫手绘：毛笔线稿，国漫画风配色，人物设计传统与现代结合",
        "90年代": "90年代复古：VHS胶片颗粒，暖黄色调，年代感街景与电视质感",
        "真人古风": "真人古风：影视级古装实拍质感，汉服妆造，传统建筑与自然四季光影",
        "现代都市": "现代都市：城市剧实拍质感，高楼街景与写字楼，真实光影",
        "像素复古": "像素复古：像素画风，复古游戏质感，硬边色块",
        "剪纸皮影": "剪纸皮影：剪纸浮雕感与皮影灯光，强对比双色剪影",
        "水墨仙侠": "水墨仙侠：水墨晕染，仙侠山水留白，空灵意境",
        "Q版萌系": "Q版萌系：三头身Q版，表情夸张可爱，圆润线条",
    }

    # 题材/导演基调（轴名 tag，与 Agnes 剧本生成·tag 输入同名）：
    # 15 个题材名与 剧本生成 tag 的接受值域逐字一致（旧 10 导演风格 + 5 补充题材）
    TAG_DESC = {
        "青春成长": "青春成长：成长主题，少年心境与自我寻找，青春语气，希望感收束",
        "家庭温馨": "家庭温馨：亲情/日常温情，暖系台词，细节打动人，治愈收束",
        "历史史诗": "历史史诗：宏大历史场面，厚重叙事，命运与抉择，史诗级蒙太奇",
        "恐怖异灵": "恐怖异灵：灵异悬疑，氛围压迫，伏笔与突现，暗调光影",
        "喜剧搞笑": "喜剧搞笑：笑点密集，角色梗多，快节奏与包袱节奏",
        "科幻未来": "科幻未来：未来世界观，科技美学，个体与人类命运的命题",
        "都市末世": "都市末世：末世求生，资源稀缺，人性考验，压迫氛围",
        "都市异能": "都市异能：现代都市+超能力体系，能力成长与爽点名场面",
        "悬疑解谜": "悬疑解谜：谜团推进，反转反转，钩子悬念层层升级",
        "逆袭爽文": "逆袭爽文：打脸反转，受气到翻盘，爽点密集",
        "甜宠CP": "甜宠CP：双向奔赴，糖点密集，误会—破冰—定情弧线，甜暖收束",
        "热血动作": "热血动作：高燃动作场面，成长与对决节奏，燃点密集",
        "治愈日常": "治愈日常：日常小事暖流，生活细节白描，轻治愈收束",
        "虐心催泪": "虐心催泪：隐忍与错位，催泪点精放，泪中带光收束",
        "喜剧沙雕": "喜剧沙雕：梗密度高，无厘头反转，笑点包袱连打",
    }

    # 节奏 3 值，与 Agnes 剧本生成·rhythm（RHYTHM_MAP）键逐字一致
    RHYTHM_DESC = {
        "快节奏": "高密度快切：钩子/笑点/爽点每 1–2 场必须出现一次，对白短促，不铺垫不拖沓",
        "中速": "标准漫剧节奏：每 3–4 场一个重点，起承转合各有一次爆发",
        "慢热": "慢烧沉浸：细节与情绪铺垫优先，钩子只放全剧 3 个转折点，对白允许带情绪",
    }

    # 情绪基调 6 值，与 Agnes 剧本生成·emotion（EMOTION_MAP）键逐字一致
    EMOTION_DESC = {
        "爽": "爽感：主角赢、解气翻身，观众痛快解压",
        "暖": "温暖：治愈暖心，观众心里一暖",
        "爆笑": "爆笑：笑点密集，观众绷不住",
        "热血": "热血：心跳加速的燃，观众被点燃",
        "紧张": "紧张：屏息揪心，观众不敢快进",
        "泪": "泪点：共情/心酸/感动，观众掉泪",
    }

    # 画幅基调（建议值进风格块文本；生图/生视频节点的 aspect_ratio API 参数归节点自持）
    ASPECT_DESC = {
        "16:9": "横屏（剧场/横屏漫剧默认）",
        "9:16": "竖屏（短剧/手机竖屏优先）",
        "1:1": "方图（角色海报/资产图优先）",
    }

    RETURN_NAMES = ("style_block", "visual_style_out", "tag_out",
                   "rhythm_out", "emotion_out", "aspect_out", "style_json")
    RETURN_TYPES = ("STRING",) * 7
    # 连线点标签：直接写目的地，用户连线时可见"该往哪接"
    RETURN_LABELS = (
        "风格说明块（接 剧本生成·风格规范块 / LLM 提示词）",
        "视觉风格（text）",
        "tag·题材（接 剧本生成·tag）",
        "节奏（接 剧本生成·rhythm）",
        "情绪（接 剧本生成·emotion）",
        "画幅（建议值进风格块）",
        "风格JSON",
    )

    OUTPUT_DOCS = {
        "style_block": "完整风格规范块（视觉+题材+节奏+情绪+画幅+补充），接 剧本生成·风格规范块 输入槽，或注入任意 LLM 提示词/文本输入",
        "visual_style_out": "所选视觉风格名（如「国风3D」）：进风格块文本；生图/视频提示词族的 style 枚举对照见其 tooltip",
        "tag_out": "题材 tag 名（15 题材）：直连 剧本生成·tag（同名同值域，连线后覆盖手输值）",
        "rhythm_out": "节奏（快节奏/中速/慢热）：直连 剧本生成·rhythm；留「不限」则本输出为空",
        "emotion_out": "情绪基调（爽/暖/爆笑/热血/紧张/泪）：直连 剧本生成·emotion；留「不限」则本输出为空",
        "aspect_out": "画幅基调（16:9/9:16/1:1）：建议值（进风格块文本）；API 级 aspect_ratio 由 生图/生视频 节点自持",
        "style_json": "机器可读 JSON：{\"visual\",\"tag\",\"extra\",\"rhythm\",\"emotion\",\"aspect\"}",
    }

    FUNCTION = "build"
    OUTPUT_NODE = True  # 自执行叶子：输出即风格说明块，便于当前直接查看/存档

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "visual_style": (list(cls.VISUAL_DESC.keys()), {
                    "label": "视觉风格",
                    "default": "二次元2D",
                    "tooltip": "视觉风格轴（画面长什么样）：10 种画风进风格块文本，全管线生图/生视频提示词遵循",
                }),
                "tag": (list(cls.TAG_DESC.keys()), {
                    "label": "tag·题材基调",
                    "default": "逆袭爽文",
                    "tooltip": "题材/导演基调轴（讲什么）：15 题材名与 剧本生成·tag 同值域；输出  tag·题材  可直连 剧本生成·tag（连线后覆盖手输值）",
                }),
            },
            "optional": {
                "extra": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "可选：追加风格要求，如「暖色调、大景深、镜头偏俯拍」",
                    "tooltip": "可选：一句话补充风格要求，与其余轴一起进入风格规范块",
                }),
                "rhythm": (["不限", "快节奏", "中速", "慢热"], {
                    "label": "节奏",
                    "default": "不限",
                    "tooltip": "节奏基调（多快）：3 值与 剧本生成·rhythm 同值域，输出可直连；「不限」= 不输出本轴（下游用节点自身默认）",
                }),
                "emotion": (["不限", "爽", "暖", "爆笑", "热血", "紧张", "泪"], {
                    "label": "情绪基调",
                    "default": "不限",
                    "tooltip": "情绪基调（观众什么感受）：6 值与 剧本生成·emotion 同值域，输出可直连；「不限」= 不输出本轴",
                }),
                "aspect": (["不限", "16:9", "9:16", "1:1"], {
                    "label": "画幅基调",
                    "default": "不限",
                    "tooltip": "画幅基调（建议值）：进风格块文本提示 LLM 族按此出画幅描述；API 级 aspect_ratio 由 生图/生视频 节点自持（不连线不生效）",
                }),
            },
        }

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "style_block" in kwargs:
            extra["style_block"] = {
                "description": "Agnes 创作风格规范（视觉风格 × 题材 × 节奏 × 情绪 × 画幅 × 补充）"
            }
        return extra

    def build(self, visual_style="二次元2D", tag="逆袭爽文", extra="",
              rhythm="不限", emotion="不限", aspect="不限") -> Tuple[str, str, str, str, str, str, str]:
        v_desc = self.VISUAL_DESC.get(visual_style, visual_style)
        t_desc = self.TAG_DESC.get(tag, tag)
        extra = (extra or "").strip()
        rhythm_v = "" if rhythm in ("", "不限") else rhythm
        emotion_v = "" if emotion in ("", "不限") else emotion
        aspect_v = "" if aspect in ("", "不限") else aspect

        lines = [
            "═══ Agnes 创作风格规范 ═══",
            f"视觉风格：{visual_style} —— {v_desc}",
            f"题材基调：{tag} —— {t_desc}",
        ]
        if rhythm_v:
            lines.append(f"节奏基调：{rhythm_v} —— {self.RHYTHM_DESC.get(rhythm_v, rhythm_v)}")
        if emotion_v:
            lines.append(f"情绪基调：{emotion_v} —— {self.EMOTION_DESC.get(emotion_v, emotion_v)}")
        if aspect_v:
            lines.append(f"画幅基调：{aspect_v} —— {self.ASPECT_DESC.get(aspect_v, aspect_v)}")
        if extra:
            lines.append(f"补充要求：{extra}")
        lines.append("后续所有资产生成（图像/视频）与分镜提示词请遵循此风格规范")
        style_block = "\n".join(lines)

        style_json = json.dumps(
            {"visual": visual_style, "tag": tag, "extra": extra,
             "rhythm": rhythm_v, "emotion": emotion_v, "aspect": aspect_v},
            ensure_ascii=False,
        )

        flags = [x for x, v in (("节奏", rhythm_v), ("情绪", emotion_v), ("画幅", aspect_v)) if v]
        print(f"[Agnes 创作风格配置] {visual_style} × {tag}"
              + (f"（+{'/'.join(flags)}）" if flags else "")
              + (f"（+补充 {len(extra)} 字）" if extra else ""))
        return (style_block, visual_style, tag,
                rhythm_v, emotion_v, aspect_v, style_json)


NODE_CLASS_MAPPINGS = {"AgnesStyleSelector": AgnesStyleSelector}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStyleSelector": "🪄 Agnes 创作风格配置"}
