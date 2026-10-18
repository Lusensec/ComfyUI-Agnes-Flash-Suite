"""
Agnes API Key Config Node
==========================
A special node that persists the user's API key to a local config file.
Run this node once to save your API key; all other Agnes nodes will
automatically pick it up when their api_key field is left empty.

Config file location: <plugin_dir>/api_key_config.json
"""

import json
import os
from typing import Tuple

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PLUGIN_DIR, "api_key_config.json")


class AgnesNovelAPIKeyConfig:
    """Persist Agnes API key to a local config file for all nodes to share."""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("status", "masked_key", "full_key")
    RETURN_LABELS = ('状态信息', '已掩码的Key', '完整Key')
    FUNCTION = "save_key"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        # Try to load existing key for display
        existing_key = ""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_key = data.get("api_key", "")
        except Exception:
            pass

        return {
            "required": {
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

    def save_key(self, api_key: str, clear_key: bool = False) -> Tuple[str, str, str]:
        """
        Save or clear the API key in the plugin config file.
        """
        if clear_key:
            # Remove config file
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
            return ("[OK] API key has been cleared from config.", "", "")

        key = api_key.strip()
        if not key:
            return ("[Error] API key is empty. Please enter a valid key.", "", "")

        # Save to JSON config file
        config_data = {"api_key": key}
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return (f"[Error] Failed to save config: {str(e)}", "", "")

        # Mask the key for display (show first 8 + last 4 chars)
        if len(key) > 12:
            masked = key[:8] + "****" + key[-4:]
        elif len(key) > 6:
            masked = key[:3] + "****" + key[-3:]
        else:
            masked = "****"

        return (
            f"[OK] API key saved to {os.path.basename(CONFIG_FILE)}. "
            f"All other Agnes nodes will now auto-load this key.",
            masked,
            key,
        )

NODE_CLASS_MAPPINGS = {"AgnesNovelAPIKeyConfig": AgnesNovelAPIKeyConfig}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesNovelAPIKeyConfig": "🔑 Agnes Novel API Key 配置"}
