"""
Agnes 分镜提示词生成节点
将分镜脚本转换为 Agnes Image API 可用的详细提示词
"""
import requests
import re
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta


class AgnesScenePromptGenerator:
    """使用 Agnes LLM 生成分镜提示词"""
    
    DESCRIPTION = "将分镜脚本转换为高质量的英文图像生成提示词，支持多种艺术风格"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "scene_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入分镜脚本...",
                    "tooltip": "从场景切分或总导演节点输出的分镜文本"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key"
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）"
                }),
                "style": (["cinematic", "anime", "realistic", "watercolor", "oil_painting"], {
                    "default": "cinematic",
                    "tooltip": "图像风格：cinematic=电影感，anime=动漫，realistic=写实，watercolor=水彩，oil_painting=油画"
                }),
            },
            "optional": {
                "characters_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "{\"characters\":[...]}",
                    "tooltip": "角色信息 JSON（从资产提取节点获取，可选）"
                }),
                "locations_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "{\"locations\":[...]}",
                    "tooltip": "场景信息 JSON（从资产提取节点获取，可选）"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("detailed_prompt", "log_text")
    RETURN_LABELS = ("英文提示词", "处理日志")
    OUTPUT_TOOLTIPS = ("英文生图提示词（风格化+角色/场景一致性描述，连接文生图/图生图节点）",
                       "处理日志（成功=字数+响应元数据；空响应=⚠️警示；失败=异常详情）")
    FUNCTION = "generate_prompt"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "detailed_prompt" in kwargs:
            extra["detailed_prompt"] = {
                "description": "转换为英文的详细图像生成提示词，包含主体描述、动作姿态、场景环境、光线设计、色彩影调、技术质量词"
            }
        if "log_text" in kwargs:
            extra["log_text"] = {
                "description": "处理日志（响应元数据/空响应警示/异常详情）"
            }
        return extra

    def generate_prompt(self, scene_text="", base_url="", api_key="", style="cinematic", model=CHAT_MODEL, characters_json="", locations_json="", reasoning_effort="auto"):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）", "API Key 缺失。")
        print(f"\n{'='*50}")
        print(f"🖼️  Agnes 分镜提示词生成")
        print(f"{'='*50}")
        print(f"输入分镜: {scene_text[:200]}...")

        prompt = f"""你是一位世界顶级的AI图像生成提示词工程师，专精于将影视分镜脚本转换为高质量的AI生图提示词。

【任务】
将以下分镜脚本转换为一个极其详细的英文生图提示词。

【输入分镜脚本】
{scene_text}

【角色信息】（如有）
{characters_json}

【场景信息】（如有）
{locations_json}

【风格要求】
{style}

【提示词生成规则】

第一部分：主体描述
- 人物姓名、性别、年龄感
- 精确的服装描述：款式、材质、颜色、纹理、配饰
- 精确的面部表情：眉毛形态、眼神方向、嘴角状态
- 精确的情绪状态
- 人物在画面中的位置

第二部分：动作与姿态
- 身体姿态
- 手部动作
- 动态或静态描述

第三部分：场景与环境
- 最远景/背景
- 中景
- 近景/前景

第四部分：光线设计
- 主光源方向与类型
- 光质
- 光影效果

第五部分：色彩与影调
- 整体色调
- 饱和度与对比度

第六部分：技术质量词
- masterpiece, best quality, 8k, highly detailed, sharp focus
- cinematic lighting, film grain, 35mm
- rule of thirds composition, deep depth of field

【输出要求】
- 只输出一个完整的英文提示词段落
- 不要有任何额外解释
- 用逗号分隔各元素
- 提示词长度 150-300 词"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.4,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )
            meta_line = format_chat_meta(meta)

            # 清理 markdown 标记
            content = (raw or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

            if not content:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或换 agnes-2.5-flash 后重试")
                print(f"[Agnes Prompt] {log}")
                return ("", log)

            log = f"✅ 生成成功: {len(content)} 字符\n· 响应元数据：{meta_line}"
            print(f"[Agnes Prompt] 生成成功: {len(content)} 字符")
            return (content, log)

        except Exception as e:
            tb = traceback.format_exc()
            log = f"❌ 分镜提示词生成失败（{type(e).__name__}）: {e}\n── 完整堆栈 ──\n{tb}"
            print(f"[Agnes Prompt] 失败: {e}")
            return ("", log)


NODE_CLASS_MAPPINGS = {"AgnesScenePromptGenerator": AgnesScenePromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScenePromptGenerator": "🎨 Agnes 分镜提示词生成"}
