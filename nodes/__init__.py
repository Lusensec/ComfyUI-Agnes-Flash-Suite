# Agnes Novel Nodes
# 静态导入所有节点，自动合并映射
#
# 注册顺序 = 前端节点库（Agnes Novel 菜单）默认显示顺序（前端"原始顺序"排序模式）：
#   ① 文本类节点（配置：API Key/风格选择 → 文本输入 → 剧本（解说/漫剧）→ 小说→提示词管线：拆分/导演/提取/提示词/拆分/对话）
#   ② 图片类节点（文生图 → 图生图 → 三视图 → 反推提示词）
#   ③ 视频类节点（文生视频 → 关键帧生视频 → 参考视频生成）

# ── 文本类节点 ─────────────────────────────────────────────
from .api_key_config import AgnesNovelAPIKeyConfig
from .style_selector import AgnesStyleSelector
from .text_input import AgnesNovelTextSource
from .script_generator import AgnesScriptGenerator
from .screenplay_generator import AgnesScreenplayGenerator
from .scene_splitter import AgnesSceneSplitter
from .director_master import AgnesDirectorMaster
from .asset_extractor import AgnesAssetExtractor
from .prompt_generator import AgnesScenePromptGenerator
from .text_split import AgnesTextSplitter
from .asset_prompt import AgnesAssetPromptGenerator
from .turnaround_prompt import AgnesTurnaroundPromptGenerator
from .string_merge import AgnesStringMerge
from .llm_chat import AgnesNovelLLMChat

# ── 图片类节点 ─────────────────────────────────────────────
from .image_gen import AgnesImageGen
from .img2img import AgnesNovelImageToImage
from .character_turnaround import AgnesSubjectTurnaround
from .image_reverse import AgnesNovelImageReverse

# ── 视频类节点 ─────────────────────────────────────────────
from .text2video import AgnesNovelTextToVideo
from .img2video import AgnesNovelImageToVideo
from .video_reference import AgnesVideoReference

# 合并所有节点映射
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 从各节点文件收集映射（顺序即菜单显示顺序）
from . import api_key_config, style_selector, text_input, script_generator, screenplay_generator, scene_splitter, director_master
from . import asset_extractor, prompt_generator, text_split, asset_prompt
from . import turnaround_prompt, string_merge, llm_chat
from . import image_gen, img2img, character_turnaround, image_reverse
from . import text2video, img2video, video_reference

# 文本类：API Key 配置 → 风格选择（配置信息，紧随 API Key）→ 文本输入（文本起点，替代灰色 PrimitiveNode）
#        → 解说剧本生成（常用入口）→ 漫剧剧本生成（分场剧本）→ 场景切分 → 总导演 → 资产提取
#        → 分镜提示词生成 → 文本拆分 → 资产提示词生成 → 三视图提示词生成 → 字符串合并 → LLM 对话
# 图片类：图像生成 → 图生图 → 三视图生成 → 图像反推提示词
# 视频类：文生视频 → 关键帧生视频 → 参考视频生成
for _mod in [
    # 文本类
    api_key_config, style_selector, text_input, script_generator, screenplay_generator, scene_splitter, director_master,
    asset_extractor, prompt_generator, text_split, asset_prompt,
    turnaround_prompt, string_merge, llm_chat,
    # 图片类
    image_gen, img2img, character_turnaround, image_reverse,
    # 视频类
    text2video, img2video, video_reference,
]:
    if hasattr(_mod, 'NODE_CLASS_MAPPINGS'):
        NODE_CLASS_MAPPINGS.update(_mod.NODE_CLASS_MAPPINGS)
    if hasattr(_mod, 'NODE_DISPLAY_NAME_MAPPINGS'):
        NODE_DISPLAY_NAME_MAPPINGS.update(_mod.NODE_DISPLAY_NAME_MAPPINGS)

print(f"[AgnesNovel] 已加载 {len(NODE_CLASS_MAPPINGS)} 个节点")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
