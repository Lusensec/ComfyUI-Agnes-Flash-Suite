# -*- coding: utf-8 -*-
"""
Agnes 参考视频生成节点（图片参考 / 音频参考）
==============================================
使用 Agnes Video 2.5-flash 的 reference 模式：
- 图片参考：最多 5 张（image_1 ~ image_5），提示词中用 <Picture N> 指代
- 音频参考：最多 3 段（audio_1 ~ audio_3），提示词中用 <Audio N> 指代
  （本地文件路径或公开 URL；本地文件自动转 Base64 Data URI，单段 <15MB）
4-12 秒时长直控（seconds 参数，完整体验）+ 固定 720P + 宽高比选择。

首尾帧关键帧模式请改用「Agnes 关键帧生视频」节点（AgnesNovelImageToVideo）。
文生视频请改用「Agnes 文生视频」节点（AgnesNovelTextToVideo）。

异步接口 + 轮询，耗时可达数分钟。
输出：MP4 保存到 ComfyUI 的 output/agnes_videos/ 目录。
"""

from typing import Tuple

from ..api import (
    AgnesClient,
    get_api_key,
    VIDEO_MODEL,
    tensor_to_pil,
)
from ._output_docs import OutputDocsMixin
from .img2video import (
    ASPECT_RATIOS,
    RESOLUTIONS,
    SECONDS_MIN,
    SECONDS_MAX,
    SECONDS_DEFAULT,
    video_size_label,
    _get_output_dir,
    _make_result,
    _error,
    _VIDEO_OUTPUT_TYPE,
)


class AgnesVideoReference(OutputDocsMixin):
    """Agnes 参考素材生视频节点：最多 5 张参考图 + 3 段参考音频（2.5-flash reference 模式）。"""

    CATEGORY = "Agnes Novel"
    RETURN_TYPES = (_VIDEO_OUTPUT_TYPE, "STRING",)
    RETURN_NAMES = ("video", "resolution",)
    RETURN_LABELS = ('视频', '分辨率')
    OUTPUT_DOCS = {
        "video": "生成的视频（MP4 保存到 ComfyUI output/agnes_videos/；输出类型随环境为 VIDEO/VHS_VIDEOINFO/路径字符串），可连接 SaveVideo 预览",
        "resolution": "视频分辨率标注：固定 720P（16:9=1280×720，9:16=720×1280，其他比例服务端自动映射，标注 720P）",
    }
    FUNCTION = "generate"
    DESCRIPTION = "参考素材生视频：最多 5 张参考图 + 3 段参考音频（Agnes Video 2.5-flash reference 模式）"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "label": "提示词",
                    "multiline": True,
                    "default": "",
                    "placeholder": "以 <Picture 1> 中的角色为参考，<Audio 1> 的节奏作为背景音乐...",
                    "tooltip": "视频描述提示词；参考图用 <Picture 1>~<Picture 5> 指代，参考音频用 <Audio 1>~<Audio 3> 指代"
                }),
                "base_url": ("STRING", {
                    "label": "请求地址",
                    "multiline": False,
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整",
                }),
                "api_key": ("STRING", {
                    "label": "API Key",
                    "multiline": False,
                    "default": "",
                    "placeholder": "sk-...",
                    "tooltip": "Agnes AI API Key（留空则跟随全局配置：环境变量 AGNES_API_KEY / api_key_config.json / config.yaml）",
                }),
                "model": ([VIDEO_MODEL], {
                    "label": "模型",
                    "default": VIDEO_MODEL,
                    "tooltip": "视频生成模型：Agnes Video 2.5-flash（reference 模式支持图片/音频参考，4-12 秒 / 720P）",
                }),
                "resolution": (RESOLUTIONS, {
                    "label": "分辨率",
                    "default": "720P",
                    "tooltip": "输出分辨率：Agnes 视频接口固定 720P（参数保留供展示与选择，目前仅此一项）",
                }),
                "aspect_ratio": (ASPECT_RATIOS, {
                    "label": "宽高比",
                    "default": "16:9",
                    "tooltip": "画面宽高比（宽:高）：16:9 横屏 / 9:16 竖屏；API 文档列 16:9/9:16（可选，缺省服务端自动处理），其他比例自动就近映射",
                }),
                "seconds": ("INT", {
                    "label": "时长（秒）",
                    "default": SECONDS_DEFAULT,
                    "min": SECONDS_MIN,
                    "max": SECONDS_MAX,
                    "step": 1,
                    "tooltip": "视频时长（秒，4-12 直控）：一镜一主动作，时长内不换场景不切镜；与 Agnes 视频提示词生成 的 duration 保持一致",
                }),
                "seed": ("INT", {
                    "label": "随机种子",
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "step": 1,
                    "control_after_generate": False,
                    "tooltip": "随机种子（0=每次随机，固定值可复现结果）；随机请用输入框旁的骰子按钮（本节点已禁用前端自动附加的「生成后控制」英文下拉）",
                }),
                "max_wait_seconds": ("INT", {
                    "label": "轮询超时",
                    "default": 600,
                    "min": 60,
                    "max": 3600,
                    "step": 30,
                    "tooltip": "视频生成轮询最长等待时间（秒，生成耗时可达数分钟）",
                }),
            },
            "optional": {
                "image_1": ("IMAGE", {
                    "label": "参考图 1",
                    "tooltip": "参考图片 1（共 5 张）：提示词中用 <Picture 1> 指代"
                }),
                "image_2": ("IMAGE", {
                    "label": "参考图 2",
                    "tooltip": "参考图片 2（可选）：提示词中用 <Picture 2> 指代"
                }),
                "image_3": ("IMAGE", {
                    "label": "参考图 3",
                    "tooltip": "参考图片 3（可选）：提示词中用 <Picture 3> 指代"
                }),
                "image_4": ("IMAGE", {
                    "label": "参考图 4",
                    "tooltip": "参考图片 4（可选）：提示词中用 <Picture 4> 指代"
                }),
                "image_5": ("IMAGE", {
                    "label": "参考图 5",
                    "tooltip": "参考图片 5（可选，上限）：提示词中用 <Picture 5> 指代"
                }),
                "audio_1": ("STRING", {
                    "label": "音频参考 1",
                    "default": "",
                    "placeholder": "C:/audio/beat.mp3 或 https://.../ref.mp3",
                    "tooltip": "音频参考 1（共 3 段）：本地音频文件路径或公开 URL（mp3/wav/m4a 等，单段<15MB）；本地文件自动转 Base64 Data URI；提示词中用 <Audio 1> 指代"
                }),
                "audio_2": ("STRING", {
                    "label": "音频参考 2",
                    "default": "",
                    "placeholder": "C:/audio/ambience.mp3",
                    "tooltip": "音频参考 2（可选）：本地路径或公开 URL；提示词中用 <Audio 2> 指代"
                }),
                "audio_3": ("STRING", {
                    "label": "音频参考 3",
                    "default": "",
                    "placeholder": "C:/audio/vocal.mp3",
                    "tooltip": "音频参考 3（可选）：本地路径或公开 URL；提示词中用 <Audio 3> 指代"
                }),
            },
        }

    def generate(
        self,
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        model: str = VIDEO_MODEL,
        resolution: str = "720P",
        aspect_ratio: str = "16:9",
        seconds: int = SECONDS_DEFAULT,
        seed: int = 0,
        max_wait_seconds: int = 600,
        image_1=None,
        image_2=None,
        image_3=None,
        image_4=None,
        image_5=None,
        audio_1: str = "",
        audio_2: str = "",
        audio_3: str = "",
    ) -> Tuple:
        # 运行时回退：widget 值为空时从全局配置（api_key_config.json 等）取 API Key
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return _error("缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置")
        if not prompt.strip():
            return _error("提示词为空：请描述视频内容")

        # 收集媒体参考：图片 5 张上限、音频 3 段上限（客户端会再截断一次）
        refs = [tensor_to_pil(x) for x in
                [image_1, image_2, image_3, image_4, image_5] if x is not None][:5]
        audios = [a for a in [audio_1, audio_2, audio_3] if a and a.strip()][:3]
        if not refs and not audios:
            return _error("没有参考素材：请至少连接一张参考图片或填写一段音频参考")

        # 分辨率固定 720P（widget 展示用）；输出标注按宽高比给出像素
        size = video_size_label(aspect_ratio)
        output_dir = _get_output_dir()

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            print(f"[Agnes Video] 参考素材: 图片 {len(refs)}/5 张, 音频 {len(audios)}/3 段")
            # reference 模式（images<=5 + audios<=3，720P，4-12 秒直控）
            video_path = client.generate_video(
                prompt=prompt.strip(),
                mode="reference",
                reference_images=refs or None,
                audio_refs=audios or None,
                model=model,
                seconds=seconds,
                aspect_ratio=aspect_ratio,
                seed=seed if seed > 0 else None,
                max_wait=max_wait_seconds,
                output_dir=output_dir,
            )

            if video_path:
                return _make_result(video_path, size)
            return _error("未返回视频", size)

        except Exception as e:
            return _error(str(e), size)


NODE_CLASS_MAPPINGS = {"AgnesVideoReference": AgnesVideoReference}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesVideoReference": "🎞️ Agnes 参考视频生成"}
