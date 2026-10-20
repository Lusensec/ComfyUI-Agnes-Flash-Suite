"""
Agnes 风格选择节点
==================
漫剧/短视频全局风格定制节点（纯本地组合，不调用 API、无需 API Key）：
两个风格轴 + 一个自由补充，组合成「风格规范」输出，供后续所有资产生成
（图像/视频/分镜提示词）统一遵循：

  - 视觉风格（visual_style）：画面长什么样——国风3D / 二次元2D / 国漫手绘 /
    90年代复古 / 真人古风 / 现代都市 / 像素复古 / 剪纸皮影 / 水墨仙侠 / Q版萌系
  - 导演风格（director_style）：故事怎么讲——青春成长 / 家庭温馨 / 历史史诗 /
    恐怖异灵 / 喜剧搞笑 / 科幻未来 / 都市末世 / 都市异能 / 悬疑解谜 / 逆袭爽文
  - 自由补充（extra，可选）：一句话追加风格要求（如"暖色调、大景深"）

输出 4 路：
  - style_block   风格说明块（可直接注入任意提示词/喂给 LLM）
  - visual_style_out / director_style_out  两个风格名（便于单独接提示词节点）
  - style_json    机器可读 JSON（{"visual":"...","director":"...","extra":"..."}）

当前独立可用：后续节点接入管线（生图/生视频自动带风格）属后续工作。
"""

import json
from typing import Tuple

from ._output_docs import OutputDocsMixin


class AgnesStyleSelector(OutputDocsMixin):
    """Agnes 风格选择节点（视觉风格 × 导演风格，纯本地组合，不调用 API）。"""

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

    DIRECTOR_DESC = {
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
    }

    RETURN_NAMES = ("style_block", "visual_style_out", "director_style_out", "style_json")
    RETURN_TYPES = ("STRING",) * 4
    RETURN_LABELS = ("风格说明块", "视觉风格", "导演风格", "风格JSON")

    OUTPUT_DOCS = {
        "style_block": "完整风格规范块（视觉+导演+补充说明），可直接注入生图/生视频提示词或喂给 LLM 对话",
        "visual_style_out": "所选视觉风格名（如「国风3D」），便于单独接提示词节点",
        "director_style_out": "所选导演风格名（如「悬疑解谜」），便于单独接剧本/分镜节点",
        "style_json": "机器可读 JSON：{\"visual\":\"...\",\"director\":\"...\",\"extra\":\"...\"}",
    }

    FUNCTION = "build"
    OUTPUT_NODE = True  # 自执行叶子：输出即风格说明块，便于当前直接查看/存档

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "visual_style": (list(cls.VISUAL_DESC.keys()), {
                    "default": "二次元2D",
                    "tooltip": "视觉风格（画面长什么样）：用于生成图片/视频等资产的画风",
                }),
                "director_style": (list(cls.DIRECTOR_DESC.keys()), {
                    "default": "家庭温馨",
                    "tooltip": "导演风格（故事怎么讲）：叙事基调、节奏与情绪设计",
                }),
            },
            "optional": {
                "extra": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "可选：追加风格要求，如「暖色调、大景深、镜头偏俯拍」",
                    "tooltip": "可选：一句话补充风格要求，与两个风格轴一起进入风格规范块",
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
                "description": "Agnes 风格规范块（视觉风格 × 导演风格 × 补充）"
            }
        return extra

    def build(self, visual_style="二次元2D", director_style="家庭温馨", extra="") -> Tuple[str, str, str, str]:
        v_desc = self.VISUAL_DESC.get(visual_style, visual_style)
        d_desc = self.DIRECTOR_DESC.get(director_style, director_style)
        extra = (extra or "").strip()

        lines = [
            "═══ Agnes 风格规范 ═══",
            f"视觉风格：{visual_style} —— {v_desc}",
            f"导演风格：{director_style} —— {d_desc}",
            f"风格组合：{visual_style} × {director_style}",
        ]
        if extra:
            lines.append(f"补充要求：{extra}")
        lines.append("后续所有资产生成（图像/视频）与分镜提示词请遵循此风格规范")
        style_block = "\n".join(lines)

        style_json = json.dumps(
            {"visual": visual_style, "director": director_style, "extra": extra},
            ensure_ascii=False,
        )

        print(f"[Agnes 风格选择] 组合：{visual_style} × {director_style}" + (f"（+补充 {len(extra)} 字）" if extra else ""))
        return (style_block, visual_style, director_style, style_json)


NODE_CLASS_MAPPINGS = {"AgnesStyleSelector": AgnesStyleSelector}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesStyleSelector": "🪄 Agnes 风格选择"}
