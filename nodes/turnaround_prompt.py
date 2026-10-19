"""
Agnes Turnaround Prompt Generator Node
======================================
把「原始主体描述/提示词」（资产提示词生成节点输出，或手动粘贴的中文/英文描述）
转成一条**完整的三视图英文生成提示词**：保留全部主体细节 + 三视图构图指令
（正/侧/背并排或场景三图纸）+ 纯主体规格（纯白背景、平光无阴影）+ 质量尾词。

设计目标：完整提示词对用户可见（输出三视图提示词槽），可先手工修改优化，
再连 Agnes 三视图生成节点（该节点不再内置任何模板，直接用输入提示词出图）。

典型接法（资产线）：
  资产提取.角色JSON → 文本拆分(第N条) → 资产提示词生成
  → 三视图提示词生成(subject_type=角色) → [输出槽查看/手工修改]
  → 三视图生成(subject_desc) → 三视图设定图
"""

from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    CHAT_MODEL,
    AVAILABLE_CHAT_MODELS,
    REASONING_EFFORTS,
    normalize_reasoning_effort,
)
from ._output_docs import OutputDocsMixin


SUBJECT_TYPES = ("角色", "物品/道具", "服装", "场景", "载具", "通用")

# 主体类型 → 三视图构图指令（英文，喂给 LLM 做合并依据）
_TURNAROUND_DIRECTIVES = {
    "角色": ("single character shown in three orthographic views arranged side by side: "
             "front view, side view (profile), back view; full body from head to toe, "
             "neutral standing pose, consistent proportions, costume and hairstyle details across all views"),
    "物品/道具": ("single item shown in three orthographic views arranged side by side: "
                  "front view, side view, back view; complete item displayed, "
                  "consistent structure and material details across all views"),
    "服装": ("full costume shown in three views arranged side by side: "
            "front view, side view, back view; outfit from head to toe, "
            "flat lay or on invisible mannequin, consistent fabric and trim details across all views"),
    "场景": ("scene shown as three orthographic sheets arranged side by side: "
             "front elevation, side elevation, top-down plan view; "
             "consistent layout, architecture/structure and material details across all views"),
    "载具": ("single vehicle shown in three orthographic views arranged side by side: "
             "front view, side view, back view; full vehicle displayed, "
             "consistent body panels, trim and detail design across all views"),
    "通用": ("single subject shown in three orthographic views arranged side by side: "
             "front view, side view, back view; complete display, consistent proportions and details"),
}

# 纯主体规格（与 资产提示词生成 节点一致）
_SPEC = ("isolated on a pure white background, even flat lighting, no shadows, "
         "no perspective distortion, no scene background elements or lighting atmosphere")
_QUALITY = "masterpiece, best quality, highly detailed, sharp details"


class AgnesTurnaroundPromptGenerator(OutputDocsMixin):
    """三视图提示词生成：原始描述 → 完整三视图英文提示词（用户可见可改）."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("three_view_prompt", "log_text")
    RETURN_LABELS = ("三视图提示词", "处理日志")
    OUTPUT_DOCS = {
        "three_view_prompt": "完整三视图英文提示词：主体全部细节 + 三视图构图指令 + 纯白背景平光无阴影 + 质量尾词。可直接连 三视图生成(subject_desc)，或复制后手工修改再填入",
        "log_text": "处理日志（成功=提示词摘要预览；失败=错误原因）",
    }
    FUNCTION = "generate"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "subject_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": '连 资产提示词生成.英文资产生成提示词，\n或手动粘贴：苏尘，20岁青年剑修，黑色长发束高马尾，白衣黑边长剑袍，左手持剑',
                    "tooltip": "原始主体描述/提示词：可连 Agnes 资产提示词生成 的英文提示词输出，或手动粘贴任意中英文主体描述",
                }),
                "subject_type": (list(SUBJECT_TYPES), {
                    "default": "角色",
                    "tooltip": "主体类型（决定三视图构图指令）：角色=全身正/侧/背 / 物品道具=三视图产品设定 / 服装=正/侧/背定妆 / 场景=正立面/侧立面/俯视 / 载具=整车三视图 / 通用",
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
            },
            "optional": {},
        }

    @classmethod
    def _build_user_prompt(cls, subject_prompt: str, subject_type: str) -> str:
        directive = _TURNAROUND_DIRECTIVES.get(subject_type, _TURNAROUND_DIRECTIVES["通用"])
        return (
            f"你是三视图设定表设计师。请把以下主体描述/提示词转成一条完整的英文三视图生成提示词。\n\n"
            f"【原始主体描述】\n{subject_prompt}\n\n"
            f"【要求】\n"
            "1. 保留原文中所有主体细节（外貌/服装/材质/结构/颜色/标记等），中文翻译成英文（专名可用拼音）"
            "；去掉原文中的「单一正面视图/single front view/正面站姿」等与三视图矛盾的单视图字样\n"
            f"2. 构图指令：{directive}\n"
            f"3. 纯主体规格：{_SPEC}\n"
            f"4. 质量尾词：{_QUALITY}\n"
            "5. 只输出最终的一段英文提示词，不要解释、不要引号、不要代码块"
        )

    @staticmethod
    def _clean_prompt(raw: str) -> str:
        import re
        t = (raw or "").strip()
        t = re.sub(r"^```[a-zA-Z]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
        t = re.sub(r"^(?:English\s*prompt|Prompt|提示词)\s*[:：]\s*", "", t, flags=re.I)
        return t.strip().strip('"')

    def generate(self, subject_prompt="", subject_type="角色",
                 base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto") -> Tuple[str, str]:
        subject_prompt = (subject_prompt or "").strip()
        if not subject_prompt:
            err = "[Error: subject_prompt 为空。请连接 Agnes 资产提示词生成的输出，或手动粘贴主体描述。]"
            print(f"[Agnes 三视图提示词] {err}")
            return (err, "未输入主体描述，已跳过。")

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]"
            print(f"[Agnes 三视图提示词] {err}")
            return (err, "API Key 缺失。")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw = client.chat(
                messages=[{"role": "user", "content": self._build_user_prompt(subject_prompt, subject_type)}],
                model=model,
                temperature=0.4,
                max_tokens=1000,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
            )
            prompt = self._clean_prompt(raw)
            log = f"✅ 三视图提示词已生成（{subject_type}）：{prompt[:60].strip()}..."
            print(log)
            return (prompt, log)
        except Exception as e:
            log = f"❌ 三视图提示词生成失败: {e}"
            print(log)
            return (f"[Error] {e}", log)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundPromptGenerator": AgnesTurnaroundPromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundPromptGenerator": "✍️ Agnes 三视图提示词生成"}
