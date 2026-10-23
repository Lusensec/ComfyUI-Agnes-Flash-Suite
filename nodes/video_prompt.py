# -*- coding: utf-8 -*-
"""
Agnes 视频提示词生成节点
========================
把单条分镜内容（画面描述/台词/风格/时长）转成 Agnes 视频模型可用的英文视频提示词
（运动 + 运镜 + 时序一致性 + 风格 + 质量词），供 3 个视频节点 prompt 输入直连：

- Agnes 关键帧生视频（mode=keyframe，默认；首帧已定，提示词只描述帧后运动）
- Agnes 文生视频（mode=text，无参考素材，提示词需完整覆盖主体/环境/运镜）
- Agnes 参考视频生成（mode=reference，提示词用 <Picture N>/<Audio N> 标记指代参考素材）

台词/旁白/音乐提示非空才注入（提示 LLM 让视频含对白/口播/氛围音乐），空槽不占篇幅。

典型接法（视频线）：
  Agnes 分镜提示词批量生成 detailed_prompt_N（英文分镜提示词）
      ─▶ Agnes 视频提示词生成（shot_text，mode=keyframe）─▶ video_prompt
      ─▶ Agnes 关键帧生视频（image=分镜图批量 image_N，prompt=video_prompt）
  批量版本：分镜提示词批量任一分段 all_prompts_1_20/_21_40/_41_60
      ─▶ Agnes 视频提示词批量生成（all_prompts，3 实例分波控 RPM）
      ─▶ 各实例 video_prompt_1..20 一对一连 关键帧生视频 prompt
"""
import re
import traceback

from ..api import (
    AgnesClient,
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
    normalize_reasoning_effort,
    format_chat_meta,
)
from .prompt_generator import STYLE_OPTIONS
from ._output_docs import OutputDocsMixin


# 视频提示词生成模式（与 3 个视频节点的素材形态一一对应）
VIDEO_PROMPT_MODES = ("keyframe", "text", "reference")

# 模式 → 生成指令块（决定提示词里该写什么、不该写什么）
_MODE_INSTRUCTIONS = {
    "keyframe": (
        "关键帧模式：视频首帧固定为参考关键帧图（已连 Agnes 关键帧生视频 的 image 输入）。"
        "提示词只描述首帧之后发生的运动、动作与运镜变化，"
        "**不要重新描述首帧中已存在的静态元素**（人物外貌/服装/场景布局），"
        "全程画面与首帧保持高度一致"
    ),
    "text": (
        "文生视频模式：没有参考素材。提示词必须完整覆盖主体动作、场景环境、光线与运镜，"
        "模型仅凭文本生成整段视频"
    ),
    "reference": (
        "参考视频模式：已连参考图片（<Picture 1>..<Picture N>）与参考视频（<Audio 1>..<Audio N>）。"
        "提示词中用 <Picture N> / <Audio N> 标记指代具体参考素材（主角默认指 <Picture 1>），"
        "只描述运动与运镜，不要重描参考素材已有细节"
    ),
}

# 质量尾词（视频专用，拼在提示词末尾）
_VIDEO_QUALITY_TAGS = "smooth motion, high quality, cinematic, no distortion, no flickering, no text artifacts"


def _clean_video_prompt(raw: str) -> str:
    """清理 LLM 输出的 markdown/前缀杂质（与 资产/三视图提示词同一套正则）。"""
    t = (raw or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    t = re.sub(r"^(?:English\s*prompt|Video\s*prompt|Prompt|提示词)\s*[:：]\s*", "", t, flags=re.I)
    return t.strip().strip('"')


def build_video_user_prompt(shot_text: str, dialogue: str, style: str, mode: str, duration: int) -> str:
    """构建中文指令（LLM 输出英文视频提示词；批量节点复用同一构建器）。"""
    mode_instr = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["keyframe"])
    dialogue_block = (dialogue or "").strip() or "（未提供台词/旁白：提示词不要虚构对白，动作描述为主）"
    return (
        "你是一位世界顶级的 AI 视频生成提示词工程师，专精于将影视分镜转换为 Agnes 视频模型的高质量英文提示词。\n\n"
        "【任务】\n"
        "将以下分镜内容转换为一条完整的英文视频生成提示词。\n\n"
        f"【分镜描述】\n{shot_text}\n\n"
        f"【台词/旁白/音乐提示】\n{dialogue_block}\n"
        "（若该段台词/旁白/音乐提示非空，提示词需体现：人物对口型/口播/氛围音乐；为空则动作描述为主，不虚构对白）\n\n"
        f"【生成模式】\n{mode_instr}\n\n"
        f"【时长】\n"
        f"约 {int(duration)} 秒（与下游 Agnes 视频节点时长设置保持一致：一镜一主动作 + 一个主运镜，"
        f"镜内不换场景、不切镜、不跳跃）\n\n"
        f"【风格】\n{style}\n\n"
        "【提示词生成规则】\n"
        "1. 主体运动：人物/主体的具体动作（位移、表情变化、与道具交互），动作量匹配时长\n"
        "2. 运镜：镜头语言（static / slow pan / tilt / track / dolly in-out / zoom / crane / handheld），一镜只用一个主运镜\n"
        "3. 运动节奏：速度与律动（slow and smooth / steady / quick and sharp / ease-in-ease-out）\n"
        "4. 时序一致性：人物外貌、服装、场景全程不漂移、不变形、不闪烁\n"
        "5. 光线氛围：与分镜描述一致（主光源/色温/光影氛围）\n"
        f"6. 质量尾词：提示词末尾加 \"{_VIDEO_QUALITY_TAGS}\"\n\n"
        "【输出要求】\n"
        "- 只输出一段完整的英文提示词\n"
        "- 不要有任何额外解释\n"
        "- 用逗号分隔各元素\n"
        "- 提示词长度 80-150 词"
    )


class AgnesVideoPromptGenerator(OutputDocsMixin):
    """视频提示词生成：单条分镜 → Agnes 视频模型英文提示词（LLM 一次调用，模式/时长/风格可配）"""

    DESCRIPTION = "单条分镜 → Agnes 视频模型英文提示词（运动+运镜+一致性+风格+质量词）：mode 对应 3 个视频节点素材形态（keyframe=关键帧生视频 / text=文生视频 / reference=参考视频生成），台词/旁白非空才注入，输出直连视频节点 prompt 输入"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True

    # ── 输出：video_prompt + log_text ──
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_prompt", "log_text")
    RETURN_LABELS = ("英文视频提示词", "处理日志")
    OUTPUT_DOCS = {
        "video_prompt": (
            "英文视频生成提示词（主体运动+运镜+运动节奏+时序一致性+光线氛围+风格+质量尾词，80-150 词）；"
            "直连 Agnes 关键帧生视频 / Agnes 文生视频 / Agnes 参考视频生成 的 prompt 输入；"
            "失败= [Error] 前缀（原因见 log_text）"
        ),
        "log_text": "处理日志（成功=提示词预览+响应元数据；空响应=⚠️警示；失败=异常详情+堆栈）",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "可连 Agnes 分镜提示词批量生成 detailed_prompt_N / 单条 all_prompts 条目，或粘贴分镜画面描述",
                    "tooltip": "分镜画面描述（中文分镜原文或英文生图提示词均可，LLM 会理解并扩写为视频提示词）",
                }),
                "dialogue": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "台词/旁白/音乐提示（可连 Agnes 剧本生成 对白行）；留空=不虚构对白",
                    "tooltip": "台词/旁白/音乐提示：非空才注入 LLM 指令（视频含对白/口播/氛围音乐），空槽不占提示词篇幅",
                }),
                "style": (list(STYLE_OPTIONS), {
                    "default": "cinematic",
                    "tooltip": "画面风格：cinematic=电影感 / anime=动漫 / realistic=写实 / watercolor=水彩 / oil_painting=油画",
                }),
                "mode": (list(VIDEO_PROMPT_MODES), {
                    "default": "keyframe",
                    "tooltip": (
                        "视频节点素材形态（决定提示词写法）：keyframe=关键帧生视频（首帧已定，只描述帧后运动，默认）"
                        " / text=文生视频（无参考，完整描述） / reference=参考视频生成（<Picture N>/<Audio N> 标记指代）"
                    ),
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 4,
                    "max": 12,
                    "step": 1,
                    "tooltip": "视频时长（秒，整批共用）：动作量与运镜节奏按此时长设计；需与下游视频节点 4-12s 设置一致",
                }),
                "base_url": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key，留空=自动加载全局配置",
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）",
                }),
            },
            "optional": {
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none / low / medium / high / max；2.0 旧模型不生效",
                }),
            },
        }

    def generate(self, shot_text="", dialogue="", style="cinematic", mode="keyframe",
                 duration=5, base_url="", api_key="", model=CHAT_MODEL,
                 reasoning_effort="auto"):
        shot_text = (shot_text or "").strip()
        if not shot_text:
            skip_msg = "[跳过] 分镜文本为空：请连接 Agnes 分镜提示词批量生成 的 detailed_prompt_N / all_prompts 单条输出，或直接粘贴分镜描述"
            print(f"[Agnes 视频提示词] {skip_msg}")
            return (skip_msg, "输入为空，已跳过。")

        api_key = str(api_key or "").strip()
        if not api_key:
            api_key = str(get_api_key() or "").strip()
        if not api_key:
            err = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 视频提示词] {err}")
            return (err, "API Key 缺失。")

        print(f"\n[Agnes 视频提示词] mode={mode} style={style} duration={duration}s")
        print(f"  分镜: {shot_text[:120]}...")

        user_prompt = build_video_user_prompt(shot_text, dialogue, style, mode, duration)
        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": user_prompt}],
                model=model,
                temperature=0.4,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )
            meta_line = format_chat_meta(meta)
            prompt = _clean_video_prompt(raw)
            if not prompt:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试")
                print(f"[Agnes 视频提示词] {log}")
                return ("", log)
            log = (f"✅ 视频提示词已生成（{mode}/{style}/{duration}s）：{prompt[:60].strip()}...\n"
                   f"· 响应元数据：{meta_line}")
            print(log)
            return (prompt, log)
        except Exception as e:
            tb = traceback.format_exc()
            log = f"❌ 视频提示词生成失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            print(f"[Agnes 视频提示词] 失败: {e}")
            return (f"[Error] {e}", log)


NODE_CLASS_MAPPINGS = {"AgnesVideoPromptGenerator": AgnesVideoPromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoPromptGenerator": "🎞️ Agnes 视频提示词生成"}
