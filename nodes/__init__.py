# Agnes Novel Nodes
# 静态导入所有节点，自动合并映射

# Novel 专用节点
from .script_generator import AgnesScriptGenerator
from .director_master import AgnesDirectorMaster
from .image_gen import AgnesImageGen
from .asset_extractor import AgnesAssetExtractor
from .scene_splitter import AgnesSceneSplitter
from .prompt_generator import AgnesScenePromptGenerator
from .video_gen import AgnesVideoGen

# 两段式管线: 资产拆分器 + 定妆图生成器
from .asset_json_splitter import AgnesAssetJsonSplitter
from .asset_maker import AgnesAssetMaker
from .jimeng_asset_maker import JimengAssetMaker

# 通用节点（Agnes Novel 版本，节点名带 Novel 前缀）
from .api_key_config import AgnesNovelAPIKeyConfig
from .llm_chat import AgnesNovelLLMChat
from .image_reverse import AgnesNovelImageReverse
from .img2img import AgnesNovelImageToImage
from .text2img import AgnesNovelTextToImage
from .img2video import AgnesNovelImageToVideo
from .text2video import AgnesNovelTextToVideo
from .video_reference import AgnesVideoReference
from .character_turnaround import AgnesSubjectTurnaround

# 合并所有节点映射
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 从各节点文件收集映射
from . import script_generator, director_master, image_gen, asset_extractor
from . import scene_splitter, prompt_generator, video_gen
from . import api_key_config, llm_chat, image_reverse
from . import img2img, text2img, img2video, text2video
from . import video_reference
from . import character_turnaround
from . import asset_json_splitter, asset_maker, jimeng_asset_maker

for _mod in [script_generator, director_master, image_gen, asset_extractor,
             scene_splitter, prompt_generator, video_gen,
             api_key_config, llm_chat, image_reverse,
             img2img, text2img, img2video, text2video,
             video_reference,
             character_turnaround,
             asset_json_splitter, asset_maker, jimeng_asset_maker]:
    if hasattr(_mod, 'NODE_CLASS_MAPPINGS'):
        NODE_CLASS_MAPPINGS.update(_mod.NODE_CLASS_MAPPINGS)
    if hasattr(_mod, 'NODE_DISPLAY_NAME_MAPPINGS'):
        NODE_DISPLAY_NAME_MAPPINGS.update(_mod.NODE_DISPLAY_NAME_MAPPINGS)

print(f"[AgnesNovel] 已加载 {len(NODE_CLASS_MAPPINGS)} 个节点")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]