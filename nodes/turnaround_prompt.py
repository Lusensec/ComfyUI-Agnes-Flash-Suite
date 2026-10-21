"""
Agnes 三视图提示词生成节点
================
把「原始主体描述/提示词」（资产提示词生成节点输出，或手动粘贴的中文/英文描述）
转成一条**完整的三视图英文生成提示词**：保留全部主体细节 + 布局指令
（左侧 1/3 区域超大特写 + 右侧 2/3 区域整齐排布三视图）+ 虚幻引擎渲染风格/PBR材质/柔和漫射光
+ 纯主体规格（纯白背景、干净极简、无阴影）+ 8K 高清质量尾词。

设计目标：完整提示词对用户可见（输出三视图提示词槽），可先手工修改优化，
再连 Agnes 三视图生成节点（该节点不再内置任何模板，直接用输入提示词出图）。

典型接法（资产线）：
  资产提取.角色JSON → 文本拆分(第N条) → 资产提示词生成
  → 三视图提示词生成(subject_type=角色) → [输出槽查看/手工修改]
  → 三视图生成(subject_desc) → 三视图设定图
（20 条并发生成请用「Agnes 三视图提示词批量生成」节点）
"""

from typing import Tuple
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
from ._output_docs import OutputDocsMixin


SUBJECT_TYPES = ("角色", "物品/道具", "服装", "场景", "载具", "通用")

# 主体类型 → 分栏布局指令（英文，喂给 LLM 做合并依据）
# 布局参考：左侧 1/3 区域超大特写 + 右侧 2/3 区域整齐排布三视图
_TURNAROUND_DIRECTIVES = {
    "角色": ("panel layout: the left one-third of the frame is an ultra-large high-resolution face close-up; "
             "the right two-thirds neatly arranged with three full-body standing views of the character: "
             "front view (Front), side view (Profile) and back view (Back); full body from head to toe, "
             "consistent proportions, costume and hairstyle details across all views"),
    "物品/道具": ("panel layout: the left one-third of the frame is a high-resolution close-up of the item's most characteristic detail; "
             "the right two-thirds neatly arranged with three views of the complete item: "
             "front view, side view and back view; consistent structure and material details across all views"),
    "服装": ("panel layout: the left one-third of the frame is a high-resolution close-up of the costume's key fabric and design details; "
             "the right two-thirds neatly arranged with three views of the full outfit: "
             "front view, side view and back view; consistent fabric and trim details across all views"),
    "场景": ("panel layout: the left one-third of the frame is a high-resolution close-up of the scene's most characteristic detail or structure; "
             "the right two-thirds neatly arranged with three orthographic sheets: "
             "front elevation, side elevation and top-down plan view; consistent layout, architecture/structure and material details across all views"),
    "载具": ("panel layout: the left one-third of the frame is a high-resolution close-up of the vehicle's most characteristic part; "
             "the right two-thirds neatly arranged with three views of the complete vehicle: "
             "front view, side view and back view; consistent body panels, trim and detail design across all views"),
    "通用": ("panel layout: the left one-third of the frame is a high-resolution close-up of the subject's most characteristic detail; "
             "the right two-thirds neatly arranged with three views of the complete subject: "
             "front view, side view and back view; consistent proportions and details across all views"),
}

# 渲染风格 + 纯主体规格 + 质量尾词（英文，随指令喂给 LLM）
_RENDER = "Unreal Engine rendered look, PBR materials, soft diffused lighting"
_SPEC = "pure white background, clean and minimal, no shadows"
_QUALITY = "8K, highly detailed, sharp textures"


class AgnesTurnaroundPromptGenerator(OutputDocsMixin):
    """三视图提示词生成：原始描述 → 完整三视图英文提示词（用户可见可改）."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("three_view_prompt", "log_text")
    RETURN_LABELS = ("三视图提示词", "处理日志")
    OUTPUT_DOCS = {
        "three_view_prompt": "完整三视图英文提示词：主体全部细节 + 分栏布局（左 1/3 特写 + 右 2/3 三视图）+ 虚幻引擎渲染/PBR/柔和漫射光 + 纯白背景干净极简无阴影 + 8K 质量尾词。可直接连 三视图生成(subject_desc)，或复制后手工修改再填入",
        "log_text": "处理日志（成功=提示词摘要+响应元数据；空响应=⚠️警示；失败=异常详情+堆栈）",
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
                    "tooltip": "主体类型（决定分栏布局指令）：角色=面部特写+全身正/侧/背 / 物品道具=细节特写+三视图 / 服装=细节特写+正/侧/背定妆 / 场景=局部特写+正立面/侧立面/俯视 / 载具=局部特写+整车三视图 / 通用",
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
            f"2. 分栏布局指令：{directive}\n"
            f"3. 渲染风格：{_RENDER}\n"
            f"4. 纯主体规格：{_SPEC}\n"
            f"5. 质量尾词：{_QUALITY}\n"
            "6. 只输出最终的一段英文提示词，不要解释、不要引号、不要代码块"
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
            err = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            print(f"[Agnes 三视图提示词] {err}")
            return (err, "API Key 缺失。")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": self._build_user_prompt(subject_prompt, subject_type)}],
                model=model,
                temperature=0.4,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )
            meta_line = format_chat_meta(meta)
            prompt = self._clean_prompt(raw)
            if not prompt:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试")
                print(f"[Agnes 三视图提示词] {log}")
                return ("", log)
            log = (f"✅ 三视图提示词已生成（{subject_type}）：{prompt[:60].strip()}...\n"
                   f"· 响应元数据：{meta_line}")
            print(log)
            return (prompt, log)
        except Exception as e:
            tb = traceback.format_exc()
            log = f"❌ 三视图提示词生成失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            print(log)
            return (f"[Error] {e}", log)


NODE_CLASS_MAPPINGS = {"AgnesTurnaroundPromptGenerator": AgnesTurnaroundPromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesTurnaroundPromptGenerator": "✍️ Agnes 三视图提示词生成"}
