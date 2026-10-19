"""
Agnes API Key 配置节点
======================
特殊节点：把用户的 API Key 和 Base URL 持久化到本地配置文件。
运行一次保存后，其他所有 Agnes 节点在留空时会自动读取。

配置文件位置：<plugin_dir>/api_key_config.json
"""

import json
import os
from typing import Tuple

from ._output_docs import OutputDocsMixin

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PLUGIN_DIR, "api_key_config.json")


class AgnesNovelAPIKeyConfig(OutputDocsMixin):
    """把 Agnes API Key 和 Base URL 持久化到本地配置文件，供所有节点共享。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("base_url", "full_key", "masked_key", "status")
    RETURN_LABELS = ('请求地址', '完整Key', '已掩码的Key', '状态信息')
    OUTPUT_DOCS = {
        "base_url": "本次保存的模型请求地址（留空时回显内置默认值）",
        "full_key": "完整 API Key（本节点内部使用；如需在其他节点手动粘贴请用此项输出）",
        "masked_key": "掩码后的 API Key（前8+****+后4），用于确认保存成功，可安全显示",
        "status": "保存/清除结果信息（成功或失败原因）",
    }
    FUNCTION = "save_key"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        # 尝试读取已有 key / base url 用于默认显示
        existing_key = ""
        existing_base_url = ""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_key = data.get("api_key", "")
                    existing_base_url = data.get("base_url", "")
        except Exception:
            pass

        return {
            "required": {
                "base_url": ("STRING", {
                    "multiline": False,
                    "default": existing_base_url or "https://api.agnes-ai.cn/v1",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "模型请求地址（动态 Base URL）。保存后所有留空的节点将使用此地址；也可用环境变量 AGNES_API_BASE_URL 或 config.yaml 的 api.base_url。",
                }),
                "api_key": ("STRING", {
                    "multiline": False,
                    "default": existing_key,
                    "placeholder": "sk-xxxxxxxx...",
                    "tooltip": "Agnes AI API Key。保存后写入插件配置，其他节点留空时自动复用。",
                }),
            },
            "optional": {
                "clear_key": ("BOOLEAN", {
                    "default": False,
                    "label_on": "是 - 清除已保存的 Key",
                    "label_off": "否 - 保存 / 更新 Key",
                    "tooltip": "选「是」时删除配置文件中已保存的 API Key。",
                }),
            },
            "hidden": {},
        }

    def save_key(self, base_url: str = "", api_key: str = "", clear_key: bool = False) -> Tuple[str, str, str, str]:
        """
        在插件配置文件中保存或清除 API Key 与 Base URL。
        """
        if clear_key:
            # 删除配置文件
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            return ("", "", "", "[OK] 已从配置中清除 API Key 与 Base URL。")

        key = api_key.strip()
        if not key:
            return ("", "", "", "[错误] API Key 为空：请输入有效的 Key")

        url = (base_url or "").strip().rstrip("/")

        # 保存到 JSON 配置文件
        config_data = {"api_key": key, "base_url": url}
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return ("", "", "", f"[错误] 保存配置失败：{str(e)}")

        # 掩码显示 Key（前 8 位 + **** + 后 4 位）
        if len(key) > 12:
            masked = key[:8] + "****" + key[-4:]
        elif len(key) > 6:
            masked = key[:3] + "****" + key[-3:]
        else:
            masked = "****"

        # 同步内存全局值，本会话后续节点立即生效
        try:
            from ..api import set_api_key, set_base_url
            set_api_key(key)
            set_base_url(url)
        except Exception:
            pass

        return (
            url or "https://api.agnes-ai.cn/v1 (default)",
            key,
            masked,
            f"[OK] API Key 已保存到 {os.path.basename(CONFIG_FILE)}"
            + (f"，Base URL = {url}" if url else "")
            + "。其他 Agnes 节点现在会自动加载此配置。",
        )

NODE_CLASS_MAPPINGS = {"AgnesNovelAPIKeyConfig": AgnesNovelAPIKeyConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelAPIKeyConfig": "🔑 Agnes API Key 配置"}
