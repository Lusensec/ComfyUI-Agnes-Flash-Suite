"""
Agnes API Key Config Node
==========================
A special node that persists the user's API key and Base URL to a local
config file. Run this node once to save your API key and request address;
all other Agnes nodes will automatically pick them up when the fields are
left empty.

Config file location: <plugin_dir>/api_key_config.json
"""

import json
import os
from typing import Tuple

from ._output_docs import OutputDocsMixin

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PLUGIN_DIR, "api_key_config.json")


class AgnesNovelAPIKeyConfig(OutputDocsMixin):
    """Persist Agnes API key and Base URL to a local config file for all nodes to share."""

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
        # Try to load existing key / base url for display
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
                    "tooltip": "Your Agnes AI API key. Will be saved to plugin config and reused by all other nodes.",
                }),
            },
            "optional": {
                "clear_key": ("BOOLEAN", {
                    "default": False,
                    "label_on": "YES - Clear saved key",
                    "label_off": "NO - Save / Update key",
                    "tooltip": "Set to YES to delete the saved API key from config.",
                }),
            },
            "hidden": {},
        }

    def save_key(self, base_url: str = "", api_key: str = "", clear_key: bool = False) -> Tuple[str, str, str, str]:
        """
        Save or clear the API key and Base URL in the plugin config file.
        """
        if clear_key:
            # Remove config file
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            return ("", "", "", "[OK] API key and Base URL have been cleared from config.")

        key = api_key.strip()
        if not key:
            return ("", "", "", "[Error] API key is empty. Please enter a valid key.")

        url = (base_url or "").strip().rstrip("/")

        # Save to JSON config file
        config_data = {"api_key": key, "base_url": url}
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return ("", "", "", f"[Error] Failed to save config: {str(e)}")

        # Mask the key for display (show first 8 + last 4 chars)
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
            f"[OK] API key saved to {os.path.basename(CONFIG_FILE)}"
            + (f", Base URL = {url}" if url else "")
            + ". All other Agnes nodes will now auto-load these settings.",
        )

NODE_CLASS_MAPPINGS = {"AgnesNovelAPIKeyConfig": AgnesNovelAPIKeyConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelAPIKeyConfig": "🔑 Agnes Novel API Key 配置"}
