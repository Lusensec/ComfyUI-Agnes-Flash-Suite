"""
Agnes LLM 对话节点
=================
与 Agnes 对话模型进行文本对话（默认 agnes-2.5-flash）。
支持通过可选的系统提示词与对话消息进行多轮交互。
"""

from typing import Any, Dict, Tuple

from ..api import AgnesClient, get_api_key, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort
from ._output_docs import OutputDocsMixin


class AgnesNovelLLMChat(OutputDocsMixin):
    """Agnes AI LLM 对话节点：与 Agnes 对话模型多轮交互（可带系统提示词）。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("response",)
    RETURN_LABELS = ('AI回复',)
    OUTPUT_DOCS = {
        "response": "Agnes 对话模型返回的完整文本（可连接任意文本节点，或直接复制使用）",
    }
    FUNCTION = "chat"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入消息...",
                    "tooltip": "要发送给 Agnes 对话模型的用户消息",
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
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key（留空则跟随全局配置：环境变量 AGNES_API_KEY / api_key_config.json / config.yaml；申请地址 platform.agnes-ai.com）",
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "Agnes chat model: agnes-2.5-flash（默认对话/视觉/工具）/ agnes-3.0-flash（Agent 编程、工具编排，Thinking 7 档）",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                    "tooltip": "采样温度（越高越发散/有创意）",
                }),
                "max_tokens": ("INT", {
                    "default": 4096,
                    "min": 1,
                    "max": 32768,
                    "step": 1,
                    "tooltip": "响应最大 token 数",
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "系统提示词指令...",
                    "tooltip": "系统提示词：设定 AI 的行为/角色",
                }),
                "enable_thinking": ("BOOLEAN", {
                    "default": False,
                    "label_on": "开启",
                    "label_off": "关闭",
                    "tooltip": "Thinking 模式：模型先思考再回答（chat_template_kwargs.enable_thinking），消耗更多 token",
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考强度：2.5-flash 支持 none/low/medium/high/max；3.0-flash 支持 7 档；auto=不传该参数（跟随模型默认）",
                }),
            },
        }

    def chat(
        self,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = CHAT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str = "",
        enable_thinking: bool = False,
        reasoning_effort: str = "auto",
    ) -> Tuple[str]:
        if not prompt.strip():
            return ("[错误] 提示词为空：请输入消息",)

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）",)

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            messages = []
            if system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt.strip()})
            messages.append({"role": "user", "content": prompt})

            ctk = {"enable_thinking": True} if enable_thinking else None
            effort = normalize_reasoning_effort(reasoning_effort)

            response = client.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                chat_template_kwargs=ctk,
                reasoning_effort=effort,
            )
            return (response,)
        except Exception as e:
            return (f"[错误] {str(e)}",)

NODE_CLASS_MAPPINGS = {"AgnesNovelLLMChat": AgnesNovelLLMChat}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelLLMChat": "💬 Agnes LLM 对话"}
