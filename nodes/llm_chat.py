"""
Agnes LLM Chat Node
===================
Enables text-based conversation with Agnes AI's LLM (agnes-2.0-flash).
Supports multi-turn dialogue via optional system prompt and conversation history.
"""

from typing import Any, Dict, Tuple

from ..api import AgnesClient, get_api_key, CHAT_MODEL, AVAILABLE_CHAT_MODELS


class AgnesNovelLLMChat:
    """Agnes AI LLM Chat node for ComfyUI."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("response",)
    RETURN_LABELS = ('AI回复',)
    FUNCTION = "chat"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Your Agnes AI API key from platform.agnes-ai.com",
                }),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter your message...",
                    "tooltip": "The user message to send to Agnes LLM",
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
                    "tooltip": "Sampling temperature (higher = more creative)",
                }),
                "max_tokens": ("INT", {
                    "default": 4096,
                    "min": 1,
                    "max": 32768,
                    "step": 1,
                    "tooltip": "Maximum number of tokens in the response",
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Optional system instructions...",
                    "tooltip": "System prompt to set behavior/role of the AI",
                }),
                "enable_thinking": ("BOOLEAN", {
                    "default": False,
                    "label_on": "开启",
                    "label_off": "关闭",
                    "tooltip": "Thinking 模式：模型先思考再回答（chat_template_kwargs.enable_thinking），消耗更多 token",
                }),
                "reasoning_effort": (["auto", "none", "low", "medium", "high", "max"], {
                    "default": "auto",
                    "tooltip": "思考强度：2.5-flash 支持 none/low/medium/high/max；3.0-flash 支持 7 档；auto=不传该参数",
                }),
            },
        }

    def chat(
        self,
        api_key: str,
        prompt: str,
        model: str = CHAT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system_prompt: str = "",
        enable_thinking: bool = False,
        reasoning_effort: str = "auto",
    ) -> Tuple[str]:
        if not prompt.strip():
            return ("[Error: Prompt is empty]",)

        # Runtime fallback: try config file if widget value is empty
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]",)

        try:
            client = AgnesClient(api_key)
            messages = []
            if system_prompt.strip():
                messages.append({"role": "system", "content": system_prompt.strip()})
            messages.append({"role": "user", "content": prompt})

            ctk = {"enable_thinking": True} if enable_thinking else None
            effort = None if reasoning_effort == "auto" else reasoning_effort

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
            return (f"[Error] {str(e)}",)

NODE_CLASS_MAPPINGS = {"AgnesNovelLLMChat": AgnesNovelLLMChat}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelLLMChat": "💬 Agnes Novel LLM 对话"}
