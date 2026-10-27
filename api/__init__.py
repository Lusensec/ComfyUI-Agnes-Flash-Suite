"""
Agnes AI API Client
==================
Wrapper for all Agnes AI API endpoints.

Endpoints:
- Chat Completions:  POST /v1/chat/completions
- Image Generation:  POST /v1/images/generations
- Video Generation:  POST /v1/video/generations (async with polling)

Supported Models:
- agnes-3.0-flash : Agent 编程/工具编排（Thinking 7 档），推荐用于复杂任务
- agnes-2.5-flash : LLM chat / vision / tools（默认文本模型，Thinking 5 档）
- agnes-2.0-flash : 旧版 LLM
- agnes-image-2.5-flash (默认): 档位 1K-4K + ratio + extra_body 多图合成（套件唯一图像模型）
- agnes-image-2.1/2.0 : 旧版 WxH 像素路径（客户端保留兼容分支，节点已不再提供选项；显式传旧模型才走该分支）
- agnes-video-2.5-flash (默认): seconds 4-12s + mode text/keyframe/reference, 720P
- agnes-video-v2.0 : 文生视频、图生视频（num_frames 轮询）
"""

import base64
import json
import os
import random
import re
import time
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
import yaml
from PIL import Image

# torch / numpy are only needed inside ComfyUI (tensor conversions).
# Lazy-import them to allow the API module to be tested standalone.
_torch = None
_np = None

def _get_torch():
    global _torch
    if _torch is None:
        import torch as _t
        _torch = _t
    return _torch

def _get_np():
    global _np
    if _np is None:
        import numpy as _n
        _np = _n
    return _np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.agnes-ai.cn/v1"
DEFAULT_CHAT_MODEL = "agnes-2.5-flash"
DEFAULT_IMAGE_MODEL = "agnes-image-2.5-flash"
DEFAULT_VIDEO_MODEL = "agnes-video-2.5-flash"

DEFAULT_SIZE = "1024x1024"
DEFAULT_VIDEO_FRAMES = 121
DEFAULT_VIDEO_FPS = 24
_DEFAULT_VIDEO_MAX_WAIT = 600  # seconds, also in config.yaml
_DEFAULT_VIDEO_POLL_INTERVAL = 10  # seconds, also in config.yaml
VIDEO_TIMEOUT = 600  # video generation can take 2-5 minutes

# Load configuration from config.yaml
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "config.yaml")

def _load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml, falling back to defaults."""
    config = {
        "base_url": DEFAULT_BASE_URL,
        "api_key": "",
        "chat_model": DEFAULT_CHAT_MODEL,
        "image_model": DEFAULT_IMAGE_MODEL,
        "video_model": DEFAULT_VIDEO_MODEL,
        "video_max_wait": _DEFAULT_VIDEO_MAX_WAIT,
        "video_poll_interval": _DEFAULT_VIDEO_POLL_INTERVAL,
    }
    try:
        if os.path.exists(_CONFIG_FILE):
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    if "api" in yaml_config and "base_url" in yaml_config["api"]:
                        config["base_url"] = yaml_config["api"]["base_url"]
                    if "api" in yaml_config and "video_max_wait" in yaml_config["api"]:
                        config["video_max_wait"] = int(yaml_config["api"]["video_max_wait"])
                    if "api" in yaml_config and "video_poll_interval" in yaml_config["api"]:
                        config["video_poll_interval"] = int(yaml_config["api"]["video_poll_interval"])
                    if "models" in yaml_config:
                        if "chat" in yaml_config["models"]:
                            config["chat_model"] = yaml_config["models"]["chat"]
                        if "image" in yaml_config["models"]:
                            config["image_model"] = yaml_config["models"]["image"]
                        if "video" in yaml_config["models"]:
                            config["video_model"] = yaml_config["models"]["video"]
                    if "api_key" in yaml_config:
                        config["api_key"] = yaml_config["api_key"] or ""
    except Exception:
        pass  # Fall back to defaults if config loading fails
    return config

_config = _load_config()

BASE_URL = _config["base_url"]
CHAT_MODEL = _config["chat_model"]
IMAGE_MODEL = _config["image_model"]
VIDEO_MODEL = _config["video_model"]
VIDEO_MAX_WAIT = _config["video_max_wait"]
VIDEO_POLL_INTERVAL = _config["video_poll_interval"]

AVAILABLE_CHAT_MODELS = list(dict.fromkeys(
    [CHAT_MODEL, "agnes-3.0-flash", "agnes-2.5-flash", "agnes-2.0-flash"]))
AVAILABLE_IMAGE_MODELS = list(dict.fromkeys(
    [IMAGE_MODEL, "agnes-image-2.5-flash"]))  # 仅保留 2.5（2.1/2.0 已下线；旧实例由 agnes-migrate.js 自动迁到 2.5）
AVAILABLE_VIDEO_MODELS = list(dict.fromkeys(
    [VIDEO_MODEL, "agnes-video-2.5-flash", "agnes-video-v2.0"]))

# 思考等级（reasoning_effort，Agnes 2.5/3.0 文本模型 Thinking 模式）：
# 2.5-flash 5 档 none~max；3.0-flash 7 档（本套件暴露其中 5 档）
# "auto" = 不传该参数，跟随模型默认思考等级
REASONING_EFFORTS = ("auto", "none", "low", "medium", "high", "max")
_REASONING_EFFORT_VALID = frozenset(("none", "low", "medium", "high", "max"))


def normalize_reasoning_effort(v):
    """节点思考等级 widget 值 → API 参数值。

    auto / 空 / 非法值（含旧 JSON 遗留脏值）→ None（不传 reasoning_effort，
    保持模型默认行为）；合法档位原样返回。
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    return s if s in _REASONING_EFFORT_VALID else None


def format_chat_meta(meta, max_tokens=None):
    """响应元数据一行摘要（finish_reason / 完成 token / 思考占比），供各 LLM 节点诊断日志使用。

    meta 来自 client.chat(return_meta=True)；传 None 也安全。
    max_tokens=None（模型自动输出模式）时不显示上限。
    空正文 + finish_reason=length 通常 = 思考模型预算耗尽。
    """
    meta = meta or {}
    usage = meta.get("usage") or {}
    if max_tokens is not None:
        cap = f"（上限 {max_tokens}）"
    else:
        cap = "（上限=模型默认）"
    line = f"finish_reason={meta.get('finish_reason')}；completion_tokens={usage.get('completion_tokens')}{cap}"
    reasoning = meta.get("reasoning_tokens")
    if reasoning:
        line = f"{line}，其中思考 {reasoning} tokens"
    return line


MIME_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
}

# ---------------------------------------------------------------------------
# 新 Flash 2.5 模型族（2026 版接口，参见 Agnes-flash-suite-skills）
# - 图像: agnes-image-2.5-flash  尺寸档位 1K/2K/3K/4K + ratio，
#   图生图/多图合成走 extra_body.image[]（URL 或 Base64 Data URI）
# - 视频: agnes-video-2.5-flash  seconds("4"~"12") + mode(text/keyframe/reference)，
#   固定 720P；首尾帧 first_frame/last_frame；images<=5；audios<=3（URL 或
#   Base64 Data URI）；查询端点需附加 &model_name=<model>
# ---------------------------------------------------------------------------
NEW_CHAT_MODELS = ("agnes-3.0-flash", "agnes-2.5-flash")
NEW_IMAGE_MODELS = ("agnes-image-2.5-flash",)
NEW_VIDEO_MODELS = ("agnes-video-2.5-flash",)

IMAGE_TIER_SIZES = ("1K", "2K", "3K", "4K")
IMAGE_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9")
# 节点上可选但新图像接口不支持的比例 → 就近映射
_IMAGE_RATIO_FALLBACK = {"4:5": "3:4", "5:4": "4:3", "9:21": "21:9"}

VIDEO_25_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
# 节点上常见但新视频接口不支持的比例 → 就近映射
_VIDEO_RATIO_FALLBACK = {"4:5": "3:4", "5:4": "4:3", "9:21": "21:9"}

# 音频参考（2.5-flash reference 模式 audios[]）：公开 URL 或 Base64 Data URI
# 本地文件按扩展名推断 MIME（免公开托管，服务端实测接受 Data URI）
_AUDIO_MIME_MAP = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".flac": "audio/flac", ".wma": "audio/x-ms-wma", ".opus": "audio/opus",
}
_AUDIO_MAX_MB = 15  # Flash 单段 < 15MB


def normalize_audio_ref(a):
    """把音频参考归一化为 API 可接受的形式。

    支持输入：
    - str 公开 URL（http/https）或 Data URI（data:）→ 原样返回
    - str 本地文件路径 → 读文件转 Base64 Data URI（MIME 按扩展名推断），
      单段超过 15MB 时抛错
    - bytes → 默认按 audio/mpeg 编码 Data URI（兼容旧调用）
    - None / 空串 → None
    """
    if a is None:
        return None
    if isinstance(a, (bytes, bytearray)):
        return "data:audio/mpeg;base64," + base64.b64encode(bytes(a)).decode("ascii")
    if isinstance(a, str):
        s = a.strip()
        if not s:
            return None
        if s.startswith(("http://", "https://", "data:")):
            return s
        if not os.path.exists(s):
            raise RuntimeError(f"[Video 错误] 音频参考文件不存在: {s}")
        with open(s, "rb") as f:
            data = f.read()
        if len(data) > _AUDIO_MAX_MB * 1024 * 1024:
            raise RuntimeError(f"[Video 错误] 音频参考超过 {_AUDIO_MAX_MB}MB 上限: {s}")
        mime = _AUDIO_MIME_MAP.get(os.path.splitext(s)[1].lower(), "audio/mpeg")
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    return None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def tensor_to_pil(tensor) -> Image.Image:
    """
    Convert a ComfyUI IMAGE tensor [B, H, W, C] (float32, 0..1) to a PIL Image.
    Returns the first image in the batch.
    """
    np = _get_np()
    # Take first image: [H, W, C]
    img = tensor[0].cpu().numpy()
    img = (img * 255).astype(np.uint8)
    return Image.fromarray(img)


def pil_to_tensor(pil_img: Image.Image):
    """Convert a PIL Image to a ComfyUI IMAGE tensor [1, H, W, C] float32."""
    torch = _get_torch()
    np = _get_np()
    img = np.array(pil_img.convert("RGB")).astype(np.float32) / 255.0
    return torch.from_numpy(img).unsqueeze(0)


def pil_to_base64_uri(pil_img: Image.Image, fmt: str = "png") -> str:
    """Convert a PIL Image to a base64 data URI string."""
    buf = BytesIO()
    pil_img.save(buf, format=fmt.upper())
    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    # Safety: ensure padding is correct (b64encode already pads, but belt-and-suspenders)
    pad = len(b64) % 4
    if pad:
        b64 += "=" * (4 - pad)
    mime = MIME_MAP.get(fmt.lower(), "image/png")
    return f"data:{mime};base64,{b64}"


def pil_to_base64_raw(pil_img: Image.Image, fmt: str = "png") -> str:
    """Convert a PIL Image to raw base64 string (no data URI prefix)."""
    buf = BytesIO()
    pil_img.save(buf, format=fmt.upper())
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    pad = len(b64) % 4
    if pad:
        b64 += "=" * (4 - pad)
    return b64


def download_url_to_pil(url: str, timeout: int = 120) -> Optional[Image.Image]:
    """Download an image from a URL and return as PIL Image."""
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception:
        pass
    return None


def download_url_to_bytes(url: str, timeout: int = 120) -> Optional[bytes]:
    """Download content from a URL and return raw bytes."""
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


# 视频结果下载重试：3 次尝试，中间等待 2/5/10 秒（短退避，任务结果已在服务端、可安全重下）
_DOWNLOAD_MAX_RETRIES = 3
_DOWNLOAD_DELAYS = [2, 5, 10]


def download_url_with_retry(url: str, timeout: int = 120,
                            max_retries: int = _DOWNLOAD_MAX_RETRIES,
                            delays: Optional[List[int]] = None) -> Tuple[Optional[bytes], str]:
    """带重试下载 URL 文件。

    返回 (bytes, 诊断信息)：
      - 成功：(bytes, "")
      - 失败：(None, 诊断)——最后一次失败的异常类型/原因或 HTTP 状态，供报错定位
    重试策略：max_retries 次尝试，中间按 delays（默认 2/5/10 秒）退避。
    空 URL / 非 200 / 0 字节 / 网络与解析异常均不吞掉，全部计入诊断。
    """
    if not url:
        return None, "video_url 为空（服务端未返回下载地址）"
    if delays is None:
        delays = _DOWNLOAD_DELAYS
    last_diag = "未知错误"
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200 and resp.content:
                return resp.content, ""
            last_diag = f"HTTP {resp.status_code}（{'空文件' if resp.status_code == 200 else '非 200'}）"
        except requests.exceptions.RequestException as e:
            last_diag = f"{type(e).__name__}: {str(e)[:200]}"
        except Exception as e:  # URL 非法（None/空串/协议缺失）等也进诊断
            last_diag = f"{type(e).__name__}: {str(e)[:200]}"
        if attempt < max_retries:
            time.sleep(delays[min(attempt - 1, len(delays) - 1)])
    return None, last_diag


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class AgnesClient:
    """Unified client for all Agnes AI API endpoints."""

    # HTTP statuses that trigger an automatic retry.
    _RETRY_STATUSES = {429, 500, 502, 503, 504, 524}
    # 队列满/限流类状态：等待时间需要分钟级（生图队列排空约 1-5 分钟）
    _QUEUE_STATUSES = {429, 503}
    _QUEUE_BASE_DELAY = 15  # 秒（指数退避: 15, 30, 60, 120）
    _MAX_RETRIES = 3
    _MAX_RETRIES_QUEUE = 5  # 队列满/限流专用：最多等 ~3.75 分钟
    _RETRY_BASE_DELAY = 3  # seconds (exponential backoff: 3, 6, 12)
    # 视频 503 队列满/限流退避：重试次数可由节点「重试次数」参数动态调整（默认 5、上限 30）
    _VIDEO_DEFAULT_RETRIES = 5   # 默认 5 次：10/30/30/30/30 秒（累计 130 秒 ≈ 2.2 分钟）
    _VIDEO_MAX_RETRIES = 30      # 上限（第 6-10 次每次 60 秒、第 11 次起每次 90 秒，30 次累计 2230 秒 ≈ 37.2 分钟）
    _VIDEO_QUEUE_DELAYS = [10, 30, 30, 30, 30]  # 默认 5 次的退避表

    @classmethod
    def _video_queue_delays(cls, retries: int) -> List[int]:
        """视频 503/429 退避表：前 5 次 10/30/30/30/30 秒（默认累计 130 秒——前段探测密集，
        视频队列常在 1-3 分钟内恢复，早 30-60s 接住；实际睡眠带 ±15% 随机抖动错峰），
        第 6-10 次每次 60 秒，第 11 次起每次 90 秒（队列满越久下一次探测命中概率越低，
        后段放宽间隔省请求、避免把 503 打成 429 限流升级）。"""
        r = max(0, int(retries))
        delays = []
        for i in range(r):
            if i < 5:
                delays.append([10, 30, 30, 30, 30][i])
            elif i < 10:
                delays.append(60)
            else:
                delays.append(90)
        return delays

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.api_key = api_key
        # 请求地址：节点传入 > 全局动态值（API Key 配置节点/环境变量/config 文件/config.yaml）
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_error(status_code: int, body_text: str, api_name: str = "API") -> str:
        """Parse an error response and return a clean, human-readable message."""
        text = body_text.strip() if body_text else ""

        # Cloudflare HTML error page
        if text.startswith("<!DOCTYPE") or text.startswith("<html"):
            # Try to extract Cloudflare error info
            title_match = re.search(r"<title>[^<]*?(\d{3}):\s*([^<]*)</title>", text)
            if title_match:
                code = title_match.group(1)
                desc = title_match.group(2)
            else:
                code = str(status_code)
                desc = "server error"

            # Map Cloudflare codes to Chinese messages
            cf_map = {
                "520": "服务器返回未知错误",
                "521": "服务器已宕机",
                "522": "连接超时（服务器未响应）",
                "523": "服务器不可达",
                "524": "服务器处理超时（任务过重）",
                "525": "SSL 握手失败",
                "526": "SSL 证书无效",
                "530": "服务器错误",
            }

            extra = cf_map.get(code, desc)
            return (
                f"[{api_name} 错误] 服务器 {extra} (HTTP {status_code})。\n"
                f"原因：Agnes AI 服务器繁忙或请求处理超时。\n"
                f"建议：稍等 1-2 分钟后重试。"
            )

        # JSON error response
        error_data = None
        try:
            if text:
                error_data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        if isinstance(error_data, dict):
            error_field = error_data.get("error")
            if isinstance(error_field, dict):
                error_msg = error_field.get("message", "")
            elif isinstance(error_field, str):
                error_msg = error_field
            else:
                error_msg = ""
            if error_msg:
                return f"[{api_name} 错误] {error_msg} (HTTP {status_code})"
            # 顶层 code/message 结构（如 {"code":"video_queue_full","message":"..."}）
            top_code = str(error_data.get("code", ""))
            top_msg = str(error_data.get("message", ""))
            if top_code == "video_queue_full":
                return (f"[{api_name} 错误] 视频队列已满，请稍后重试（HTTP {status_code}）。"
                        f"{top_msg}")
            if top_code or top_msg:
                return f"[{api_name} 错误] {top_code + ': ' if top_code else ''}{top_msg} (HTTP {status_code})"

        # Fallback: truncate long responses
        if len(text) > 300:
            text = text[:300] + "..."
        return f"[{api_name} 错误] HTTP {status_code}: {text}" if text else f"[{api_name} 错误] HTTP {status_code}"

    def _request_with_retry(self, method: str, url: str, api_name: str,
                            json_payload: dict = None, timeout: int = 300,
                            max_retries: Optional[int] = None,
                            queue_delays: Optional[List[int]] = None,
                            queue_hint: Optional[str] = None) -> requests.Response:
        """Make an HTTP request with automatic retry on transient server errors.

        队列满/限流（429/503）默认采用分钟级退避（15/30/60/120 秒，最多
        _MAX_RETRIES_QUEUE 次）；传入 queue_delays 则按指定秒数序列退避
        （视频提交用 10/30/30/30/30，第 6-10 次每次 60 秒、第 11 次起每次 90 秒，
        睡眠带 ±15% 随机抖动；503/429 响应带 Retry-After 头时优先按该头指定秒数；
        次数由节点「重试次数」参数控制）；
        queue_hint 覆盖队列满建议文案。其他可重试状态维持 3/6/12 秒短退避（120 秒封顶）。
        """
        max_retries = max_retries or self._MAX_RETRIES
        last_error = None
        total_waited = 0
        for attempt in range(1, max_retries + 1):
            try:
                if method == "POST":
                    resp = self.session.post(url, json=json_payload, timeout=timeout)
                else:
                    resp = self.session.get(url, timeout=timeout)

                if resp.status_code == 200:
                    return resp

                if resp.status_code in self._RETRY_STATUSES and attempt < max_retries:
                    if resp.status_code in self._QUEUE_STATUSES:
                        if queue_delays:
                            delay = queue_delays[min(attempt - 1, len(queue_delays) - 1)]
                            # ±15% 随机抖动：与其他 503 等待者的探测错峰，避免队列恢复瞬间同步重探（惊群）
                            delay = max(1, int(delay * random.uniform(0.85, 1.15)))
                        else:
                            delay = self._QUEUE_BASE_DELAY * (2 ** (attempt - 1))
                        # 服务端若随 503/429 给出 Retry-After 头，优先按服务端指定秒数退避
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(1, int(float(retry_after)))
                                print(f"[Agnes] {resp.status_code} 响应带 Retry-After={retry_after} 秒，按服务端指定退避")
                            except ValueError:
                                pass
                    else:
                        delay = min(self._RETRY_BASE_DELAY * (2 ** (attempt - 1)), 120)
                    last_error = (resp.status_code, resp.text)
                    time.sleep(delay)
                    total_waited += delay
                    continue

                # Not retryable or last attempt → raise
                if resp.status_code in self._QUEUE_STATUSES:
                    hint = (queue_hint or "建议：生图队列繁忙（文生图与图生图队列相互独立），"
                            "请等 5-10 分钟后再运行本节点。")
                    raise RuntimeError(self._clean_error(resp.status_code, resp.text, api_name) +
                                       f"\n（已自动重试 {attempt - 1} 次、累计等待约 {total_waited} 秒）"
                                       f"\n{hint}")
                raise RuntimeError(self._clean_error(resp.status_code, resp.text, api_name))

            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    delay = min(self._RETRY_BASE_DELAY * (2 ** (attempt - 1)), 120)
                    time.sleep(delay)
                    total_waited += delay
                    continue
                raise RuntimeError(
                    f"[{api_name} 错误] 请求超时 (>{timeout}秒)。\n"
                    f"建议：Agnes 服务器可能繁忙，请稍后重试。"
                )
            except requests.exceptions.ConnectionError:
                if attempt < max_retries:
                    delay = min(self._RETRY_BASE_DELAY * (2 ** (attempt - 1)), 120)
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"[{api_name} 错误] 无法连接到 Agnes 服务器。\n"
                    f"建议：请检查网络连接或访问 https://platform.agnes-ai.cn/ 确认服务状态。"
                )

        # Should not reach here, but handle gracefully
        if last_error:
            raise RuntimeError(self._clean_error(last_error[0], last_error[1], api_name))
        raise RuntimeError(f"[{api_name} 错误] 请求失败（已重试 {max_retries} 次）")

    # ------------------------------------------------------------------
    # Chat / LLM
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str = CHAT_MODEL,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        chat_template_kwargs: Optional[Dict[str, Any]] = None,
        reasoning_effort: Optional[str] = None,
        return_meta: bool = False,
    ):
        """Call the chat completions endpoint.

        return_meta=True 时返回 (content, meta) 元组：meta 含 finish_reason /
        usage（总消耗与思考 token 明细）等响应元数据，用于诊断空响应、
        思考预算耗尽等问题；False（默认）保持旧行为，仅返回 content 字符串。

        max_tokens 默认 None = 不传该参数，输出长度上限由模型/服务端默认决定，
        模型自然停止（finish_reason=stop）；仅在需要显式限制输出长度时传值。
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        # Thinking 模式（2.5-flash 5 档 none~max；3.0-flash 7 档）
        if chat_template_kwargs:
            payload["chat_template_kwargs"] = chat_template_kwargs
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        resp = self._request_with_retry("POST", url, "Chat", json_payload=payload)

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise RuntimeError(f"[Chat 错误] 意外的响应格式: {data}")
        if not return_meta:
            return content
        usage = data.get("usage") or {}
        reasoning_tokens = (
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            or (data["choices"][0].get("message") or {}).get("reasoning_tokens")
        )
        meta = {
            "finish_reason": data["choices"][0].get("finish_reason"),
            "usage": usage,
            "reasoning_tokens": reasoning_tokens,
            "model": data.get("model"),
        }
        return content, meta

    # ------------------------------------------------------------------
    # Image Generation
    # ------------------------------------------------------------------

    def generate_image(
        self,
        prompt: str,
        mode: str = "text2img",
        reference_images: Optional[List[Image.Image]] = None,
        size: str = DEFAULT_SIZE,
        n: int = 1,
        model: str = IMAGE_MODEL,
        ratio: Optional[str] = None,
        return_base64: bool = False,
    ) -> List[Image.Image]:
        """Generate images via the Agnes image generation API.

        支持两代接口（按 size 传参自动区分，无需指定模型）：
        - 新接口 agnes-image-2.5-flash：size 传档位 "1K"/"2K"/"3K"/"4K"，
          可选 ratio（1:1,3:4,4:3,16:9,9:16,2:3,3:2,21:9）；
          图生图/多图合成通过 extra_body.image[] 传参考图（URL 或 Base64 Data URI）；
          return_base64=True 时响应为 b64_json，直接解码为 PIL。
        - 旧接口 agnes-image-2.1/2.0：size 传 "WxH" 像素串。
        """
        url = f"{self.base_url}/images/generations"
        tier = str(size).strip().upper()
        tier_mode = tier in IMAGE_TIER_SIZES
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }

        if tier_mode:
            # 新接口 agnes-image-2.5-flash：档位 size + ratio；API 不支持 n/seed/strength
            payload["size"] = tier
            if ratio:
                payload["ratio"] = _IMAGE_RATIO_FALLBACK.get(ratio, ratio)
            if mode == "img2img" and reference_images:
                uris = [
                    img if isinstance(img, str) else pil_to_base64_uri(img)
                    for img in reference_images
                ]
                payload["extra_body"] = {
                    "image": uris,
                    "response_format": "b64_json" if return_base64 else "url",
                }
        else:
            # 旧接口 agnes-image-2.1/2.0：WxH 像素，支持 n
            payload["size"] = size
            payload["n"] = n
            if mode == "img2img" and reference_images:
                image_uris = [pil_to_base64_uri(img) for img in reference_images]
                payload["extra_body"] = {
                    "image": image_uris,
                    "response_format": "url",
                }

        # 生图队列满（503）/限流（429）：分钟级退避重试（15/30/60/120 秒）
        resp = self._request_with_retry(
            "POST", url, "Image", json_payload=payload,
            max_retries=self._MAX_RETRIES_QUEUE)

        data = resp.json()
        images = []
        for item in data.get("data", []):
            b64 = item.get("b64_json")
            if b64:
                raw = base64.b64decode(b64)
                images.append(Image.open(BytesIO(raw)).convert("RGB"))
                continue
            image_url = item.get("url") or item.get("image_url")
            if image_url:
                pil_img = download_url_to_pil(image_url)
                if pil_img:
                    images.append(pil_img)

        if not images:
            raise RuntimeError("[Image 错误] 服务器未返回任何图片，请尝试修改提示词或重试。")

        return images

    # ------------------------------------------------------------------
    # Video Generation (async with polling)
    # ------------------------------------------------------------------

    def generate_video(
        self,
        prompt: str,
        mode: str = "text2video",
        reference_images: Optional[List[Image.Image]] = None,
        model: str = VIDEO_MODEL,
        num_frames: int = DEFAULT_VIDEO_FRAMES,
        frame_rate: int = DEFAULT_VIDEO_FPS,
        seed: Optional[int] = None,
        size: Optional[str] = None,
        max_wait: int = 600,
        output_dir: Optional[str] = None,
        seconds: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        first_frame=None,
        last_frame=None,
        audio_refs: Optional[List] = None,
        return_ids: bool = False,
        retries: Optional[int] = None,
    ) -> Optional[str]:
        """
        Generate a video via the Agnes video generation API.

        支持两代接口（按 model 自动区分）：

        - 新 agnes-video-2.5-flash（4-12 秒 720P）：
            payload: seconds("4"~"12", 默认"5") + mode(text|keyframe|reference)
            + size="720P" + aspect_ratio；
            keyframe 模式: first_frame / last_frame（URL 或 Base64 Data URI）；
            reference 模式: images<=5、audios<=3（URL 或 Base64 Data URI）；
            查询: GET /agnesapi?video_id=<ID>&model_name=<model>。
        - 旧 agnes-video-v2.0：
            payload: num_frames(8n+1, <=441)/frame_rate/width/height；
            查询: GET /agnesapi?video_id=<ID>。

        Args:
            prompt: 视频描述。
            mode: 旧接口 "text2video"/"img2video"；新接口 "text"/"keyframe"/"reference"
                   （"text2video"→"text"、"img2video"→"reference" 自动映射）。
            reference_images: PIL 参考图列表；新接口 keyframe 取 [0]=首帧 [1]=尾帧，
                   reference 模式作为 images[]（最多取 5 张）。
            seconds: 新接口视频时长（秒，4-12，默认 5）。
            aspect_ratio: 新接口宽高比（21:9/16:9/4:3/1:1/3:4/9:16；其他值就近映射）。
            first_frame / last_frame: 新接口 keyframe 模式首尾帧（PIL/URL/bytes）。
            audio_refs: 新接口音频参考（公开 URL / 本地文件路径 / bytes，最多 3 个；
                    本地文件自动转 Base64 Data URI，单段 <15MB）。
            return_ids: True 时返回 (save_path, task_id, video_id) 三元组。
            retries: 提交遇 503 队列满/429 限流的自动重试次数（None=默认 5；
                    退避 10/30/30/30/30 秒，第 6-10 次每次 60 秒、第 11 次起每次 90 秒，
                    睡眠带 ±15% 随机抖动；上限 30）。
        """
        new_model = model in NEW_VIDEO_MODELS

        # --- Build submission payload ---
        url = f"{self.base_url}/videos"
        payload: Dict[str, Any] = {"model": model, "prompt": prompt}

        if new_model:
            secs = int(seconds if seconds is not None else 5)
            payload["seconds"] = str(min(12, max(4, secs)))
            m = {"text2video": "text", "img2video": "reference"}.get(mode, mode)
            if m not in ("text", "keyframe", "reference"):
                m = "text"
            payload["mode"] = m
            payload["size"] = "720P"
            ar = aspect_ratio or "16:9"
            payload["aspect_ratio"] = _VIDEO_RATIO_FALLBACK.get(ar, ar)
            payload["n"] = 1
            if seed is not None:
                payload["seed"] = seed

            def _enc_ref(v):
                """参考素材编码：str 原样（URL 或 Data URI），bytes→PNG，PIL→Data URI"""
                if isinstance(v, str):
                    return v
                if isinstance(v, (bytes, bytearray)):
                    return "data:image/png;base64," + base64.b64encode(bytes(v)).decode("ascii")
                return pil_to_base64_uri(v)

            if m == "keyframe":
                ff = first_frame if first_frame is not None else (
                    reference_images[0] if reference_images else None)
                lf = last_frame if last_frame is not None else (
                    reference_images[1] if reference_images and len(reference_images) > 1 else None)
                if ff is not None:
                    payload["first_frame"] = _enc_ref(ff)
                if lf is not None:
                    payload["last_frame"] = _enc_ref(lf)
            elif m == "reference":
                if reference_images:
                    payload["images"] = [_enc_ref(i) for i in reference_images[:5]]
                if audio_refs:
                    audios = [x for x in (normalize_audio_ref(a) for a in audio_refs[:3]) if x]
                    if audios:
                        payload["audios"] = audios
        else:
            # 旧接口 agnes-video-v2.0
            # Validate num_frames
            if (num_frames - 1) % 8 != 0:
                raise ValueError("num_frames must satisfy (num_frames - 1) % 8 == 0")
            if num_frames > 441:
                raise ValueError("num_frames must be <= 441")
            payload["num_frames"] = num_frames
            payload["frame_rate"] = frame_rate
            width = None
            height = None
            if size:
                try:
                    parts = size.split("x")
                    width = int(parts[0])
                    height = int(parts[1])
                except (ValueError, IndexError):
                    pass  # fall through, API will use defaults
            if width is not None:
                payload["width"] = width
            if height is not None:
                payload["height"] = height
            if seed is not None:
                payload["seed"] = seed
            # Image-to-video: single image or multi-image via extra_body
            if mode == "img2video" and reference_images:
                image_uris = [pil_to_base64_raw(img) for img in reference_images]
                if len(image_uris) == 1:
                    payload["image"] = image_uris[0]
                else:
                    payload["extra_body"] = {
                        "image": image_uris,
                    }

        # --- Submit task ---
        # 视频队列满/限流（429/503）：按「重试次数」参数动态退避
        # （默认 5 次 10/30/30/30/30 秒，累计 130 秒；第 6-10 次 60 秒、第 11 次起 90 秒，睡眠带 ±15% 抖动）
        n_retries = (self._VIDEO_DEFAULT_RETRIES if retries is None
                     else max(0, min(int(retries), self._VIDEO_MAX_RETRIES)))
        q_delays = self._video_queue_delays(n_retries)
        resp = self._request_with_retry(
            "POST", url, "Video", json_payload=payload, timeout=60,
            max_retries=n_retries + 1,
            queue_delays=q_delays,
            queue_hint="建议：视频生成队列繁忙（视频与生图队列相互独立），"
                       "请等 5-10 分钟后再运行本节点。")
        data = resp.json()

        task_id = data.get("id")
        video_id = data.get("video_id", task_id)  # Prefer video_id for polling
        if not task_id:
            raise RuntimeError(f"[Video 错误] 服务器未返回任务ID: {data}")

        # --- Poll for result ---
        # 新接口需附加 model_name；轮询策略：先等 60s（任务排队期），之后每 5s 一次
        status_url = f"{self.base_url}/agnesapi?video_id={video_id}"
        if new_model:
            status_url += f"&model_name={model}"
        poll_interval = 60 if (new_model and max_wait > 90) else VIDEO_POLL_INTERVAL
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            poll_interval = 5 if new_model else VIDEO_POLL_INTERVAL

            try:
                status_resp = self.session.get(status_url, timeout=30)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                continue

            if status_resp.status_code != 200:
                continue

            status_data = status_resp.json()
            state = status_data.get("status")

            if state == "completed":
                # Try multiple possible locations for the video URL
                # （新接口结果在 metadata.url / url）
                video_url = None
                for sub in ("metadata", "result", "output"):
                    obj = status_data.get(sub, {})
                    if isinstance(obj, dict):
                        for key in ("url", "video_url"):
                            val = obj.get(key)
                            if val and isinstance(val, str) and val.startswith("http"):
                                video_url = val
                                break
                    if video_url:
                        break
                if not video_url:
                    for key in ("video_url", "url", "output_url", "download_url"):
                        val = status_data.get(key)
                        if val and isinstance(val, str) and val.startswith("http"):
                            video_url = val
                            break
                if not video_url:
                    # Check data array
                    for item in status_data.get("data", []):
                        for key in ("url", "video_url"):
                            val = item.get(key)
                            if val and isinstance(val, str) and val.startswith("http"):
                                video_url = val
                                break
                        if video_url:
                            break

                if not video_url:
                    # Dump raw response for debugging
                    resp_dump = str(status_data)
                    if len(resp_dump) > 600:
                        resp_dump = resp_dump[:600] + "..."
                    raise RuntimeError(
                        f"[Video 错误] 任务状态为 completed，但未找到 video_url。\n"
                        f"API 原始响应: {resp_dump}"
                    )

                # Download and save（自动 3 次重试 2/5/10 秒；失败时附 URL 与诊断，
                # 任务结果仍在服务端，URL 有效期内可手动抢救）
                video_bytes, dl_diag = download_url_with_retry(video_url, timeout=120)
                if not video_bytes:
                    raise RuntimeError(
                        f"[Video 错误] 视频文件下载失败（已自动重试 {_DOWNLOAD_MAX_RETRIES} 次，{dl_diag}）。\n"
                        f"video_url: {video_url}\n"
                        f"task_id: {task_id}，video_id: {video_id}\n"
                        f"建议：若上方链接仍在有效期内，可用浏览器（可换直连/代理）手动下载；否则重跑本节点。"
                    )

                save_dir = output_dir if output_dir else tempfile.gettempdir()
                os.makedirs(save_dir, exist_ok=True)
                timestamp = int(time.time())
                mode_tag = str(payload.get("mode", mode)) if new_model else str(mode)
                filename = f"agnes_video_{mode_tag}_{timestamp}_{task_id[:8]}.mp4"
                save_path = os.path.join(save_dir, filename)
                with open(save_path, "wb") as f:
                    f.write(video_bytes)

                if return_ids:
                    return (save_path, task_id, video_id)
                return save_path

            elif state in ("failed", "error"):
                error_msg = status_data.get("error", "Unknown error")
                # Clean up nested error dicts
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                # Detect common server errors for user-friendly advice
                hint = ""
                error_lower = str(error_msg).lower()
                if "cuda out of memory" in error_lower or "oom" in error_lower:
                    hint = "\n原因：Agnes 服务器 GPU 显存不足，当前排队人数较多。\n建议：调低时长（seconds）或稍后重试。"
                elif "no available channel" in error_lower or "503" in error_lower:
                    hint = "\n原因：Agnes 视频模型无可用计算节点。\n建议：稍等 2-5 分钟后重试。"
                raise RuntimeError(f"[Video 错误] 视频生成失败: {error_msg}{hint}")

        raise TimeoutError(
            f"[Video 错误] 视频生成超时（已等待 {max_wait} 秒，任务ID: {task_id}，video_id: {video_id}）。\n"
            f"建议：调低时长（seconds）或调大 max_wait_seconds，或稍后重试。"
        )

    # ------------------------------------------------------------------
    # Video task split flow: submit (async submit) / collect (poll + download)
    # ------------------------------------------------------------------

    def submit_video_task(
        self,
        prompt: str,
        model: str = VIDEO_MODEL,
        seconds: Optional[int] = None,
        aspect_ratio: Optional[str] = None,
        seed: Optional[int] = None,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """异步两段式·提交段：只提交视频任务（新接口 text 模式，4-12 秒 720P），
        不做轮询与下载，秒级返回任务句柄。退避/重试与 generate_video 完全一致
        （提交遇 503 队列满/429 限流按「重试次数」动态退避，默认 5 次 10/30/30/30/30 秒，睡眠带 ±15% 抖动）。

        返回 dict:
            ok: bool 提交是否成功
            task_url: 完整轮询 URL（含域名，/agnesapi?video_id=…&model_name=…；
                      域名取自 self.base_url，提交节点可填非官方域时照常拼对）
            status: 成功="submitted: video_id=…"；失败="failed: <服务端错误响应/诊断>"
        """
        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "seconds": str(min(12, max(4, int(seconds if seconds is not None else 5)))),
            "mode": "text",
            "size": "720P",
            "aspect_ratio": _VIDEO_RATIO_FALLBACK.get(aspect_ratio or "16:9", aspect_ratio or "16:9"),
            "n": 1,
        }
        if seed is not None:
            payload["seed"] = seed

        n_retries = (self._VIDEO_DEFAULT_RETRIES if retries is None
                     else max(0, min(int(retries), self._VIDEO_MAX_RETRIES)))
        q_delays = self._video_queue_delays(n_retries)
        try:
            resp = self._request_with_retry(
                "POST", f"{self.base_url}/videos", "Video", json_payload=payload,
                timeout=60, max_retries=n_retries + 1, queue_delays=q_delays,
                queue_hint="建议：视频生成队列繁忙（视频与生图队列相互独立），"
                           "请等 5-10 分钟后再运行本节点。")
            data = resp.json()
        except Exception as e:
            return {"ok": False, "task_url": "",
                    "status": f"failed: {str(e) or type(e).__name__}"}

        task_id = data.get("id")
        video_id = data.get("video_id", task_id)
        if not task_id:
            return {"ok": False, "task_url": "",
                    "status": f"failed: 服务器未返回任务ID: {str(data)[:200]}"}

        # 完整轮询 URL（含域名）：与 generate_video 的轮询地址同一拼法，
        # 收取节点拿到它就能跨域名独立查询，无需再知道 base_url
        task_url = f"{self.base_url}/agnesapi?video_id={video_id}&model_name={model}"
        return {"ok": True, "task_url": task_url,
                "status": f"submitted: video_id={video_id}"}

    def collect_video_task(
        self,
        task_url: str,
        timeout: int = 1800,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """异步两段式·收取段：对完整轮询 URL（提交节点输出的 task_url）轮询查询，
        completed 后自动下载保存到本地。不做提交——URL 自带域名，跨域名可用。

        轮询节奏与新接口一致：首查前等 60s（任务排队期），之后每 5s 一次；
        查询遇网络抖动自动跳过本轮继续；timeout 内未完成=processing（不算失败，
        可再次调用继续查）。

        返回 dict:
            status: "completed" / "failed" / "processing"
            video_url: completed 时的服务端视频 URL
            save_path: completed 且下载成功时的本地 mp4 路径
            error: failed 时的服务端错误响应内容
        """
        timeout = max(60, int(timeout or 1800))
        elapsed = 0
        # 新接口轮询节奏：先等 60s（任务排队期），之后每 5s 一次（timeout≤90s 时首查 10s，同 generate_video）
        interval = 60 if timeout > 90 else min(VIDEO_POLL_INTERVAL, 10)
        while elapsed < timeout:
            time.sleep(min(interval, max(1, timeout - elapsed)))
            elapsed += interval
            interval = 5
            try:
                status_resp = self.session.get(task_url, timeout=30)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                continue
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()
            state = status_data.get("status")

            if state == "completed":
                video_url = None
                for sub in ("metadata", "result", "output"):
                    obj = status_data.get(sub, {})
                    if isinstance(obj, dict):
                        for key in ("url", "video_url"):
                            val = obj.get(key)
                            if val and isinstance(val, str) and val.startswith("http"):
                                video_url = val
                                break
                    if video_url:
                        break
                if not video_url:
                    for key in ("video_url", "url", "output_url", "download_url"):
                        val = status_data.get(key)
                        if val and isinstance(val, str) and val.startswith("http"):
                            video_url = val
                            break
                if not video_url:
                    for item in status_data.get("data", []):
                        for key in ("url", "video_url"):
                            val = item.get(key)
                            if val and isinstance(val, str) and val.startswith("http"):
                                video_url = val
                                break
                        if video_url:
                            break
                if not video_url:
                    resp_dump = str(status_data)
                    if len(resp_dump) > 600:
                        resp_dump = resp_dump[:600] + "..."
                    return {"status": "failed", "video_url": "", "save_path": "",
                            "error": f"任务状态为 completed，但未找到 video_url。API 原始响应: {resp_dump}"}

                video_bytes, dl_diag = download_url_with_retry(video_url, timeout=120)
                if not video_bytes:
                    return {"status": "failed", "video_url": video_url, "save_path": "",
                            "error": (f"视频文件下载失败（已自动重试 {_DOWNLOAD_MAX_RETRIES} 次，{dl_diag}）。"
                                      f"video_url: {video_url}；若链接仍在有效期内可手动下载")}
                save_dir = output_dir if output_dir else tempfile.gettempdir()
                os.makedirs(save_dir, exist_ok=True)
                filename = f"agnes_video_collect_{int(time.time())}_{abs(hash(task_url)) % 10**8}.mp4"
                save_path = os.path.join(save_dir, filename)
                with open(save_path, "wb") as f:
                    f.write(video_bytes)
                return {"status": "completed", "video_url": video_url,
                        "save_path": save_path, "error": ""}

            if state in ("failed", "error"):
                error_msg = status_data.get("error", "Unknown error")
                if isinstance(error_msg, dict):
                    error_msg = error_msg.get("message", str(error_msg))
                return {"status": "failed", "video_url": "", "save_path": "",
                        "error": f"视频生成失败: {error_msg}"}

        return {"status": "processing", "video_url": "", "save_path": "",
                "error": f"已等待 {timeout} 秒任务未完成，可再次运行本节点继续查询"}

    # ------------------------------------------------------------------
    # Image Understanding / Reverse Prompt (via vision chat)
    # ------------------------------------------------------------------

    def reverse_prompt(
        self,
        image: Image.Image,
        model: str = CHAT_MODEL,
        detail: str = "detailed",
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """
        Analyze an image and generate a prompt that could reproduce it.

        Args:
            image: Input PIL Image.
            model: Vision-capable model identifier.
            detail: "brief" or "detailed" analysis level.
            reasoning_effort: Optional thinking level ("none"-"max"; auto/None=模型默认).

        Returns:
            Generated prompt / description.
        """
        image_uri = pil_to_base64_uri(image)

        if detail == "detailed":
            system_prompt = (
                "You are an expert at analyzing images and writing prompts for "
                "AI image generation models. Describe the image in extreme detail: "
                "subject, composition, lighting, color palette, style, mood, camera angle, "
                "depth of field, textures, and any distinctive elements. "
                "Output ONLY the prompt, no additional commentary."
            )
        else:
            system_prompt = (
                "You are an expert at analyzing images and writing prompts for "
                "AI image generation models. Write a concise prompt describing the key "
                "elements of this image. Output ONLY the prompt, no additional commentary."
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_uri}},
                    {
                        "type": "text",
                        "text": "Please describe this image as an AI image generation prompt.",
                    },
                ],
            },
        ]

        return self.chat(
            messages,
            model=model,
            temperature=0.3,
            reasoning_effort=normalize_reasoning_effort(reasoning_effort),
        )


# ---------------------------------------------------------------------------
# Global state helper (shared across nodes)
# ---------------------------------------------------------------------------

# Path to the persistent API key config file (in plugin root).
# _PLUGIN_DIR is now defined above in _load_config()
_API_KEY_CONFIG_FILE = os.path.join(_PLUGIN_DIR, "api_key_config.json")

_GLOBAL_CONFIG: Dict[str, Any] = {
    "api_key": os.environ.get("AGNES_API_KEY", "") or _config.get("api_key", ""),
    "base_url": os.environ.get("AGNES_API_BASE_URL", ""),
    "chat_model": CHAT_MODEL,
    "image_model": IMAGE_MODEL,
    "video_model": VIDEO_MODEL,
}

# Attempt to load API key from config file on module init.
# Priority: env var > config file.
def _load_key_from_config_file() -> str:
    """Try to load the API key from the plugin's api_key_config.json."""
    try:
        if os.path.exists(_API_KEY_CONFIG_FILE):
            with open(_API_KEY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("api_key", "")
    except Exception:
        pass
    return ""


def _load_base_url_from_config_file() -> str:
    """Try to load the Base URL from the plugin's api_key_config.json."""
    try:
        if os.path.exists(_API_KEY_CONFIG_FILE):
            with open(_API_KEY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("base_url", "")
    except Exception:
        pass
    return ""

# Load from config file if env var not set.
if not _GLOBAL_CONFIG["api_key"]:
    _GLOBAL_CONFIG["api_key"] = _load_key_from_config_file() or _config.get("api_key", "")


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) > 12:
        return key[:8] + "****" + key[-4:]
    elif len(key) > 6:
        return key[:3] + "****" + key[-3:]
    return "****"

def get_api_key() -> str:
    # 1. Env var has highest priority
    key = os.environ.get("AGNES_API_KEY", "").strip()
    if key:
        print(f"[AgnesAPI] API Key source: env var AGNES_API_KEY = {_mask_key(key)}")
        return key
    # 2. Read from api_key_config.json
    key = _load_key_from_config_file().strip()
    if key:
        _GLOBAL_CONFIG["api_key"] = key
        print(f"[AgnesAPI] API Key source: api_key_config.json = {_mask_key(key)}")
        return key
    # 3. Read from config.yaml
    yaml_key = _config.get("api_key", "").strip()
    if yaml_key:
        _GLOBAL_CONFIG["api_key"] = yaml_key
        print(f"[AgnesAPI] API Key source: config.yaml = {_mask_key(yaml_key)}")
        return yaml_key
    # 4. Fallback to cached value
    cached = _GLOBAL_CONFIG["api_key"].strip()
    if cached:
        print(f"[AgnesAPI] API Key source: global cache = {_mask_key(cached)}")
    else:
        print("[AgnesAPI] No API Key found in any source (env var, api_key_config.json, config.yaml, cache)")
    return cached


def set_api_key(key: str) -> None:
    _GLOBAL_CONFIG["api_key"] = key


def get_base_url() -> str:
    """获取当前生效的 Base URL（动态，优先级从高到低）：
    1. 内存全局值（set_base_url / API Key 配置节点 写入）
    2. 环境变量 AGNES_API_BASE_URL
    3. api_key_config.json 的 base_url 字段
    4. config.yaml 的 api.base_url（模块导入时读取）
    5. 默认 DEFAULT_BASE_URL
    """
    # 1. 内存全局
    cached = _GLOBAL_CONFIG.get("base_url", "").strip()
    if cached:
        return cached.rstrip("/")
    # 2. 环境变量
    env_url = os.environ.get("AGNES_API_BASE_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    # 3. api_key_config.json
    file_url = _load_base_url_from_config_file().strip()
    if file_url:
        _GLOBAL_CONFIG["base_url"] = file_url
        print(f"[AgnesAPI] Base URL source: api_key_config.json = {file_url}")
        return file_url.rstrip("/")
    # 4/5. config.yaml / 默认
    return (BASE_URL or DEFAULT_BASE_URL).rstrip("/")


def set_base_url(url: str) -> None:
    """动态设置全局 Base URL；传空字符串清除（回落到环境变量/配置文件/默认值）。"""
    url = (url or "").strip().rstrip("/")
    _GLOBAL_CONFIG["base_url"] = url
    print(f"[AgnesAPI] Base URL set to: {url or '(cleared, use default)'}")


def get_client() -> AgnesClient:
    key = get_api_key()
    if not key:
        raise ValueError(
            "Agnes API key is not set. Please provide your API key in the node settings.\n"
            "Get a free key at: https://platform.agnes-ai.cn/"
        )
    return AgnesClient(key)


def get_global_config() -> Dict[str, Any]:
    return dict(_GLOBAL_CONFIG)


def set_global_model(model_type: str, model_name: str) -> None:
    _GLOBAL_CONFIG[model_type] = model_name
