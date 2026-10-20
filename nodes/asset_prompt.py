"""
Agnes Asset Prompt Generator Node
==================================
把单条资产 JSON（角色/道具/服装/场景/载具）转成可直接生图的英文提示词。
内置 art-director 模板（按 subject_type 换构图指令 + style 风格尾词 + quality 词），
免去手写 LLM 指令。

典型接法（资产线）：
  Agnes 资产提取.角色JSON → Agnes 文本拆分(JSON 数组模式)
  → 第 N 条 → Agnes 资产提示词生成(subject_type=角色, style=cinematic)
  → english_prompt → Agnes 文生图 / 三视图生成(subject_desc)
每条资产一个节点实例（各占 1 次 LLM 调用）；想省调用可改用
LLM 对话批量路线（整份 JSON 一次出全部【名】英文提示词，再接文本拆分）。
"""

import re
import traceback
from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
    normalize_reasoning_effort,
    format_chat_meta,
)
from ._output_docs import OutputDocsMixin


SUBJECT_TYPES = ("角色", "物品/道具", "服装", "场景", "载具", "通用")
STYLE_OPTIONS = ("cinematic", "anime", "realistic", "watercolor", "oil_painting")

# 主体类型 → 构图指令（英文，拼进提示词；纯主体 + 单一正面视图，从头到尾完整可见）
_SUBJECT_DIRECTIVES = {
    "角色": "single front view of the character, facing the camera, full body from head to toe completely visible, standing pose, isolated on a plain white background",
    "物品/道具": "single front view of the prop, showing its front side and full extent, isolated on a plain white background",
    "服装": "costume shown in a single front view, full outfit from head to toe, flat lay or on invisible mannequin, isolated on a plain white background",
    "场景": "single straight-on wide view of the location as a self-contained asset, showing architecture and environment clearly",
    "载具": "single front view of the vehicle, full extent visible, isolated on a plain white background",
    "通用": "single front view of the subject, full extent visible, isolated on a plain white background",
}

# style → 风格尾词（只描述画面风格，不含背景/打光/镜头）
_STYLE_TAGS = {
    "cinematic": "cinematic look",
    "anime": "anime style, clean lineart, cel shading, vibrant colors",
    "realistic": "photorealistic",
    "watercolor": "watercolor illustration, soft washes, paper texture, delicate",
    "oil_painting": "oil painting, impasto brushstrokes, rich texture",
}

_QUALITY_TAGS = "masterpiece, best quality, highly detailed"


class AgnesAssetPromptGenerator(OutputDocsMixin):
    """Agnes asset prompt generator node (JSON 资产 → 英文生图提示词)."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("english_prompt", "log_text")
    RETURN_LABELS = ("英文资产生成提示词", "处理日志")
    OUTPUT_DOCS = {
        "english_prompt": "可直接用于 文生图/三视图(subject_desc) 的英文提示词：保留 JSON 全部描述字段 + 主体构图指令 + 风格尾词 + quality 词；失败时返回 [Error] 前缀",
        "log_text": "处理日志（成功=摘要预览+响应元数据；空响应=⚠️警示；失败=异常详情+堆栈）",
    }
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": '{"name":"苏尘","sex":"男","appearance":"黑发，青色衣袍"}\n（单条资产 JSON）',
                    "tooltip": "单条资产 JSON：连 Agnes 文本拆分的任一输出槽，或手动粘贴一个资产 JSON 对象（角色/道具/服装/场景/载具字段均可）",
                }),
                "subject_type": (list(SUBJECT_TYPES), {
                    "default": "角色",
                    "tooltip": "主体类型（决定构图指令）：角色=全身设定图 / 物品道具=特写静物 / 服装=定妆服装图 / 场景=全景建立镜头 / 载具=四分之三视角 / 通用",
                }),
                "style": (list(STYLE_OPTIONS), {
                    "default": "cinematic",
                    "tooltip": "生图风格尾词：cinematic=电影感 / anime=动漫 / realistic=写实 / watercolor=水彩 / oil_painting=油画",
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
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none / low / medium / high / max；2.0 旧模型不生效",
                }),
                "max_tokens": ("INT", {
                    "default": 2000,
                    "min": 256,
                    "max": 8192,
                    "step": 128,
                    "tooltip": "输出 token 预算上限：资产提示词正文约需 150-300；思考模型下思考链与正文共享该预算，reasoning_effort≥medium 时建议调大（4000+）防空正文；勿超模型硬上限",
                }),
            },
            "optional": {},
        }

    @classmethod
    def _build_user_prompt(cls, asset_json: str, subject_type: str, style: str) -> str:
        directive = _SUBJECT_DIRECTIVES.get(subject_type, _SUBJECT_DIRECTIVES["通用"])
        style_tags = _STYLE_TAGS.get(style, "")
        return (
            f"你是一位电影美术指导。请把以下{subject_type}资产 JSON 转成一条高质量的英文图像生成提示词。\n\n"
            f"【资产 JSON】\n{asset_json}\n\n"
            f"【要求】\n"
            "1. JSON 中的姓名/性别/年龄/外貌/服装/性格/描述等字段全部保留并翻译成英文（专名可用拼音）\n"
            f"2. 构图指令：{directive}\n"
            "3. 这是资产设定图：**画面中只出现该主体本身，不要添加任何场景背景、打光氛围、镜头参数或环境元素描述**"
            "（主体自身的固有属性，如角色穿着、道具材质，正常保留）\n"
            "4. **视角：只保留主体的正面单一视图（从头到尾完整可见），不要侧面/背面/俯视/三视图/多角度并排**\n"
            f"5. 风格尾词：{style_tags}\n"
            f"6. 质量尾词：{_QUALITY_TAGS}\n"
            "7. 只输出最终的一段英文提示词，不要解释、不要引号、不要代码块"
        )

    @staticmethod
    def _clean_prompt(raw: str) -> str:
        t = (raw or "").strip()
        t = re.sub(r"^```[a-zA-Z]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
        t = re.sub(r"^(?:English\s*prompt|Prompt|提示词)\s*[:：]\s*", "", t, flags=re.I)
        return t.strip().strip('"')

    def generate(self, asset_json="", subject_type="角色", style="cinematic",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto",
                 max_tokens=2000) -> Tuple[str, str]:
        asset_json = (asset_json or "").strip()
        if not asset_json:
            err = "[错误] asset_json 为空：请连接 Agnes 文本拆分的输出槽，或手动粘贴单条资产 JSON"
            print(f"[Agnes 资产提示词] {err}")
            return (err, "未输入资产 JSON，已跳过。")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 资产提示词] {err}")
            return (err, "API Key 缺失。")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": self._build_user_prompt(asset_json, subject_type, style)}],
                model=model,
                temperature=0.4,
                max_tokens=max_tokens,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )
            meta_line = format_chat_meta(meta, max_tokens)
            prompt = self._clean_prompt(raw)
            if not prompt:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或调大 max_tokens 后重试")
                print(f"[Agnes 资产提示词] {log}")
                return ("", log)
            log = (f"✅ 资产提示词已生成（{subject_type}/{style}，预算 {max_tokens} tokens）：{prompt[:60].strip()}...\n"
                   f"· 响应元数据：{meta_line}")
            print(log)
            return (prompt, log)
        except Exception as e:
            tb = traceback.format_exc()
            log = f"❌ 资产提示词生成失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            print(log)
            return (f"[Error] {e}", log)


NODE_CLASS_MAPPINGS = {"AgnesAssetPromptGenerator": AgnesAssetPromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetPromptGenerator": "🖌️ Agnes 资产提示词生成"}
