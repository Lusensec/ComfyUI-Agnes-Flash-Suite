"""
Agnes LLM 对话节点
=================
与 Agnes 对话模型进行文本对话（默认 agnes-2.5-flash）。
纯用户消息交互：无系统提示词输入（角色/行为设定请写在「提示词」消息内）。
"""

from typing import Any, Dict, Tuple
import traceback

from ..api import AgnesClient, get_api_key, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta, FOLLOW_GLOBAL, resolve_chat_params
from ._output_docs import OutputDocsMixin


class AgnesNovelLLMChat(OutputDocsMixin):
    """Agnes AI LLM 对话节点：与 Agnes 对话模型对话（纯用户消息，无系统提示词输入；角色/行为设定写在「提示词」内）；「重试次数/请求超时」可 widget 调（长思考拉高超时）。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("response", "log_text")
    RETURN_LABELS = ('AI回复', '响应日志')
    OUTPUT_DOCS = {
        "response": "Agnes 对话模型返回的完整文本（可连接任意文本节点，或直接复制使用）",
        "log_text": "响应日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常详情+堆栈）",
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
                "model": (AVAILABLE_CHAT_MODELS + [FOLLOW_GLOBAL], {
                    "default": FOLLOW_GLOBAL,
                    "tooltip": "Agnes chat model: agnes-2.5-flash（默认对话/视觉/工具）/ agnes-3.0-flash（Agent 编程、工具编排，Thinking 7 档）；选「跟随全局（默认）」= 解析「Agnes API Key 配置」的全局对话模型（未配置则回落 2.5-flash）",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.05,
                    "tooltip": "采样温度（越高越发散/有创意）；0=跟随全局（Key 配置节点设置时），否则回落节点默认",
                }),
            },
            "optional": {
                "enable_thinking": ("BOOLEAN", {
                    "default": False,
                    "label_on": "开启",
                    "label_off": "关闭",
                    "tooltip": "Thinking 模式：模型先思考再回答（chat_template_kwargs.enable_thinking），消耗更多 token",
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考强度：2.5-flash 支持 none/low/medium/high/max；3.0-flash 支持 7 档；auto=不传该参数（跟随模型默认）；auto/空 = 跟随全局（Key 配置节点设置时），否则跟随模型默认",
                }),
                "retries": ("INT", {
                    "label": "重试次数",
                    "default": 3,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                    "tooltip": "失败重试次数（0=不重试，请求一次即止）：429 限流/5xx 服务端错误自动退避重试（3/6/12s…），默认 3；最坏总时长≈(1+重试次数)×请求超时",
                }),
                "timeout": ("INT", {
                    "label": "请求超时（秒）",
                    "default": 300,
                    "min": 30,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "单次 API 调用等待上限（秒），默认 300：长思考模式（thinking 高档位）/长上下文可拉高到 3600",
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
        system_prompt: str = "",  # 保留签名位（旧实例 widget 值按位传入不崩），运行时不再使用
        enable_thinking: bool = False,
        reasoning_effort: str = "auto",
        retries: int = 3,
        timeout: int = 300,
    ) -> Tuple[str, str]:
        if not prompt.strip():
            return ("[错误] 提示词为空：请输入消息", "提示词为空，已跳过。")

        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）", "API Key 缺失。")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            model, temperature, reasoning_effort = resolve_chat_params(model, temperature, reasoning_effort, fallback_temperature=0.7)
            messages = []
            # 无系统提示词输入（已移除）：角色/行为设定由用户写在「提示词」消息内
            messages.append({"role": "user", "content": prompt})

            ctk = {"enable_thinking": True} if enable_thinking else None
            effort = normalize_reasoning_effort(reasoning_effort)

            response, meta = client.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                chat_template_kwargs=ctk,
                reasoning_effort=effort,
                return_meta=True,
                retries=retries,
                timeout=timeout,
            )
            meta_line = format_chat_meta(meta)
            if not (response or "").strip():
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试")
                print(f"[Agnes LLM 对话] {log}")
                return ("", log)
            log = f"✅ 回复完成（{len(response)} 字）\n· 响应元数据：{meta_line}"
            print(f"[Agnes LLM 对话] 完成 {len(response)} 字")
            return (response, log)
        except Exception as e:
            tb = traceback.format_exc()
            log = f"❌ 调用失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            print(f"[Agnes LLM 对话] 失败: {e}")
            return (f"[错误] {str(e)}", log)

NODE_CLASS_MAPPINGS = {"AgnesNovelLLMChat": AgnesNovelLLMChat}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelLLMChat": "💬 Agnes LLM 对话"}
