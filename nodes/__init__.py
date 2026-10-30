# Agnes Novel Nodes
# 静态导入所有节点，自动合并映射
#
# 注册顺序 = 前端节点库（Agnes Novel 菜单）默认显示顺序（前端"原始顺序"排序模式）：
#   ① 文本类节点（配置：API Key/API Key 池配置 → 风格选择 → 文本输入 → LLM 对话/字符串合并（通用文本工具，紧随文本输入）
#      → 剧本（解说/漫剧）→ 分镜管线：拆分/导演/提取 → 资产·三视图·分镜 提示词批量 → 视频提示词（单个/批量））
#   ② 图片类节点（图像反推提示词 置顶 → 文生图 → 图生图 → 三视图 → 三视图批量 → 分镜图批量 → 图像拼图）
#   ③ 视频类节点（文生视频 → 关键帧生视频 → 参考视频生成 → 视频任务提交
#      → 视频任务并发提交（多端点 Key 池·顺序短路）→ 视频任务多任务并发提交（all_prompts 合并输入，提示词串行 × 池短路）
#      → 视频任务收取（单任务）→ 视频任务批量收取（all_task_url_keys 合并输入优先 + ≤20 任务线程池并发收取，异步两段式））

# ── 文本类节点 ─────────────────────────────────────────────
from .api_key_config import AgnesNovelAPIKeyConfig
from .api_key_pool import AgnesApiKeyPool
from .style_selector import AgnesStyleSelector
from .text_input import AgnesNovelTextSource
from .llm_chat import AgnesNovelLLMChat
from .string_merge import AgnesStringMerge
from .script_generator import AgnesScriptGenerator
from .screenplay_generator import AgnesScreenplayGenerator
from .scene_splitter import AgnesSceneSplitter
from .director_master import AgnesDirectorMaster
from .asset_extractor import AgnesAssetExtractor
from .text_split import AgnesTextSplitter
from .asset_prompt import AgnesAssetPromptGenerator
from .asset_prompt_batch import AgnesAssetPromptBatch
from .turnaround_prompt import AgnesTurnaroundPromptGenerator
from .turnaround_prompt_batch import AgnesTurnaroundPromptBatch
from .prompt_generator import AgnesScenePromptGenerator
from .scene_prompt_batch import AgnesScenePromptBatch
from .video_prompt import AgnesVideoPromptGenerator
from .video_prompt_batch import AgnesVideoPromptBatch

# ── 图片类节点 ─────────────────────────────────────────────
from .image_reverse import AgnesNovelImageReverse
from .image_gen import AgnesImageGen
from .img2img import AgnesNovelImageToImage
from .character_turnaround import AgnesSubjectTurnaround
from .turnaround_batch import AgnesTurnaroundBatch
from .scene_image_batch import AgnesSceneImageBatch
from .image_mosaic import AgnesImageMosaic

# ── 视频类节点 ─────────────────────────────────────────────
from .text2video import AgnesNovelTextToVideo
from .img2video import AgnesNovelImageToVideo
from .video_reference import AgnesVideoReference
from .video_task_submit import AgnesVideoTaskSubmit
from .video_task_submit_pool import AgnesVideoTaskSubmitPool
from .video_task_submit_batch import AgnesVideoTaskSubmitBatch
from .video_task_collect import AgnesVideoTaskCollect
from .video_task_collect_batch import AgnesVideoTaskCollectBatch

# 合并所有节点映射
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 从各节点文件收集映射（顺序即菜单显示顺序）
from . import api_key_config, api_key_pool, style_selector, text_input, llm_chat, string_merge
from . import script_generator, screenplay_generator, scene_splitter, director_master
from . import asset_extractor, text_split, asset_prompt, asset_prompt_batch
from . import turnaround_prompt, turnaround_prompt_batch, prompt_generator, scene_prompt_batch
from . import video_prompt, video_prompt_batch
from . import image_reverse, image_gen, img2img, character_turnaround, turnaround_batch, scene_image_batch, image_mosaic
from . import text2video, img2video, video_reference, video_task_submit, video_task_submit_pool, video_task_submit_batch, video_task_collect, video_task_collect_batch

# 文本类：API Key 配置 → API Key 池配置（多端点 Key 池 JSON，供 视频任务并发提交；配置信息，紧随 API Key）→ 风格选择 → 文本输入（文本起点，替代灰色 PrimitiveNode）
#        → LLM 对话（通用对话工具）→ 字符串合并（文本拼接工具）
#        → 解说剧本生成（常用入口）→ 漫剧剧本生成（分场剧本）
#        → 场景切分 → 总导演 → 资产提取
#        → 文本拆分（all_items 全部条目 JSON 输出）→ 资产提示词生成 → 资产提示词批量生成（all_items 合并输入 → all_prompts）
#        → 三视图提示词生成 → 三视图提示词批量生成（all_prompts 合并输入 → all_turnaround_prompts）
#        → 分镜提示词生成 → 分镜提示词批量生成（分镜管线末端，接 总导演/场景切分 all_scenes 合并输出，JSON 数组；
#           60 路 detailed_prompt + all_prompts + 3 路分段 all_prompts_1_20/_21_40/_41_60）
#        → 视频提示词生成（单条分镜 → 视频模型英文提示词，mode 对应 3 视频节点素材形态）
#        → 视频提示词批量生成（all_prompts 一根线各连 分镜提示词批量 任一分段，3 实例分波控 RPM；
#           20 路 video_prompt + all_video_prompts 全部视频提示词 JSON）
# 图片类：图像反推提示词（位于 图像生成 上方）→ 图像生成 → 图生图 → 三视图生成 → 三视图批量生成
#        （all_prompts 合并输入 → all_images 批量张量 (N,H,W,3)）
#        → 分镜图批量生成（分镜线 3 波出 60 镜全量：all_prompts 一根线各连 分镜提示词批量 任一分段
#           all_prompts_1_20/_21_40/_41_60（3 实例分波控 RPM；≤20 条 all_prompts 直连单实例），
#           20 路并发出关键帧 + all_images 批量张量 (N,H,W,3) 每波总览）
#        → 图像拼图（位于 分镜图批量 之后，batch_images 批量张量总输入优先 / 批量图 20 路 → 1 路拼图）
# 视频类：文生视频 → 关键帧生视频 → 参考视频生成 → 视频任务提交（异步提交段）
#        → 视频任务并发提交（多端点 Key 池·顺序短路：池 JSON 输入替代 base_url+api_key，
#           按池序逐条目试探、命中即停零浪费，retries 机制同 单提交；task_url_key 胜出 Key 随行，
#           批量收取 零改动直连；pool_report 逐条目 JSON 矩阵（人工查看/接 LLM 对话做台账）；
#           面板输出顺序 task_url→api_key→task_url_key→pool_report→status（status 置最下））
#        → 视频任务多任务并发提交（all_prompts 合并输入：直连 视频提示词批量 all_video_prompts
#           （JSON 数组 ≤20），外层提示词串行循环 × 内层池 Key 顺序短路（复用 并发提交 机制，
#           绝不同双提示词并发）；单条失败=该槽 0 标记继续下一条；20 路 task_url_key_i（成功=单线
#           双参 JSON / 失败="0" / 空槽=""）+ status 整批状态 JSON + all_task_url_keys 20 元素保位
#           JSON 数组（一根线直连 批量收取 all_task_url_keys 合并输入），输出顺序对齐 视频提示词批量）
#        → 视频任务收取（单任务收片）→ 视频任务批量收取（all_task_url_keys 合并输入置顶优先
#           （直连 多任务并发提交 all_task_url_keys，按序填充 task_1..20 槽）/ 20 个 task_i 逐一连线
#           （task_i ↔ video_i，提交节点 task_url_key 单线双参 0 中间节点直连；"0" 条目跳过记 error
#           并默认视频占位填充）；线程池并发 ≤20 任务，20 路 video + 整批状态 JSON + 全部视频路径 JSON）
for _mod in [
    # 文本类
    api_key_config, api_key_pool, style_selector, text_input,
    llm_chat, string_merge,
    script_generator, screenplay_generator, scene_splitter, director_master,
    asset_extractor, text_split, asset_prompt, asset_prompt_batch,
    turnaround_prompt, turnaround_prompt_batch, prompt_generator, scene_prompt_batch,
    video_prompt, video_prompt_batch,
    # 图片类
    image_reverse, image_gen, img2img, character_turnaround, turnaround_batch, scene_image_batch,
    image_mosaic,
    # 视频类
    text2video, img2video, video_reference,
    video_task_submit, video_task_submit_pool, video_task_submit_batch,
    video_task_collect, video_task_collect_batch,
]:
    if hasattr(_mod, 'NODE_CLASS_MAPPINGS'):
        NODE_CLASS_MAPPINGS.update(_mod.NODE_CLASS_MAPPINGS)
    if hasattr(_mod, 'NODE_DISPLAY_NAME_MAPPINGS'):
        NODE_DISPLAY_NAME_MAPPINGS.update(_mod.NODE_DISPLAY_NAME_MAPPINGS)

print(f"[AgnesNovel] 已加载 {len(NODE_CLASS_MAPPINGS)} 个节点")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
