"""
Agnes 分镜提示词生成节点
将分镜脚本转换为 Agnes Image API 可用的详细提示词
资产信息（角色/场景/服装/道具/天气 JSON，来自 Agnes 资产提取）非空才注入，
空槽不占提示词篇幅（避免模型对着空标题块自行脑补）
"""
import requests
import re
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta


# 图像风格（与 资产/三视图提示词节点同一套；批量节点共用导入）
STYLE_OPTIONS = ("cinematic", "anime", "realistic", "watercolor", "oil_painting")


class AgnesScenePromptGenerator:
    """使用 Agnes LLM 生成分镜提示词"""
    
    DESCRIPTION = "将分镜脚本转换为高质量的英文图像生成提示词，支持多种艺术风格；可选注入 资产提取 的角色/场景/服装/道具/天气 5 路 JSON 保跨镜一致性"

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
                "style": (list(STYLE_OPTIONS), {
                    "default": "cinematic",
                    "tooltip": "图像风格：cinematic=电影感，anime=动漫，realistic=写实，watercolor=水彩，oil_painting=油画"
                }),
            },
            "optional": {
                "characters_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "[{\"name\":\"角色名\",\"gender\":\"男/女\",\"appearance\":\"外貌描述\"}]",
                    "tooltip": "角色信息 JSON（从资产提取节点获取，可选）；留空=不注入该信息块"
                }),
                "locations_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "[{\"name\":\"场景名\",\"description\":\"环境描述\",\"era\":\"时代背景\"}]",
                    "tooltip": "场景信息 JSON（从资产提取节点获取，可选）；留空=不注入该信息块"
                }),
                "costumes_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "[{\"character\":\"角色名\",\"description\":\"服装描述\"}]",
                    "tooltip": "服装信息 JSON（从资产提取节点获取，可选）；留空=不注入该信息块"
                }),
                "props_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "[\"道具1\", \"道具2\"]",
                    "tooltip": "道具列表 JSON（从资产提取节点获取，可选）；留空=不注入该信息块"
                }),
                "weather_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "[\"天气/氛围 1\", \"天气/氛围 2\"]",
                    "tooltip": "天气/氛围 JSON（从资产提取节点获取，可选）；留空=不注入该信息块"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
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
                "description": "转换为英文的详细图像生成提示词，包含主体描述、动作姿态、场景环境与构图/镜头语言、光线设计、色彩影调、风格化质量词（对齐 Agnes 官方文生图结构：主体+场景+风格+光照+构图+质量）"
            }
        if "log_text" in kwargs:
            extra["log_text"] = {
                "description": "处理日志（响应元数据/空响应警示/异常详情）"
            }
        return extra

    def generate_prompt(self, scene_text="", base_url="", api_key="", style="cinematic", model=CHAT_MODEL, characters_json="", locations_json="", costumes_json="", props_json="", weather_json="", reasoning_effort="auto", retries=3, timeout=300):
        if not (scene_text or "").strip():
            skip_msg = "[跳过] 分镜文本为空：请连接 Agnes 总导演 / Agnes 场景切分 的分镜输出，或直接粘贴分镜文本"
            print(f"[Agnes 分镜提示词] {skip_msg}")
            return (skip_msg, "输入为空，已跳过。")
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            return ("[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）", "API Key 缺失。")
        print(f"\n{'='*50}")
        print(f"🖼️  Agnes 分镜提示词生成")
        print(f"{'='*50}")
        print(f"输入分镜: {scene_text[:200]}...")

        # 资产信息注入（角色/场景/服装/道具/天气，来自 Agnes 资产提取 5 路 JSON）：
        # 只注入非空块，空槽不占篇幅（避免模型对着空标题块自行脑补）
        _asset_blocks = [
            ("角色信息", characters_json),
            ("场景信息", locations_json),
            ("服装信息", costumes_json),
            ("道具信息", props_json),
            ("天气氛围", weather_json),
        ]
        _kept = [(name, (val or "").strip()) for name, val in _asset_blocks if (val or "").strip()]
        if _kept:
            asset_block = "\n\n".join(f"【{name}】\n{val}" for name, val in _kept)
        else:
            asset_block = "（未连接资产信息：仅依据分镜脚本描述，不自行脑补外貌/服装细节）"
        print(f"资产注入: {('、'.join(name for name, _ in _kept)) if _kept else '无'}")

        prompt = f"""你是一位世界顶级的AI图像生成提示词工程师，专精于将影视分镜脚本转换为高质量的AI生图提示词。

【任务】
将以下分镜脚本转换为一个极其详细的英文生图提示词。

【输入分镜脚本】
{scene_text}

【资产信息】（来自 资产提取，非空才注入；其中角色/服装/场景描述必须沿用，不得自行改写）
{asset_block}

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

第三部分：场景、环境与构图（镜头语言）
- 最远景/背景（各列 1-3 个具体细节）
- 中景（列 1-3 个具体细节）
- 近景/前景（列 1-3 个具体细节）
- 镜头语言：景别（大远景/全景/中景/近景/特写/大特写）、机位角度（平视/仰拍/俯拍/鸟瞰/贴地）、镜头焦段感（广角/标准/长焦）

第四部分：光线设计
- 主光源方向与类型
- 光质
- 光影效果

第五部分：色彩与影调
- 整体色调
- 饱和度与对比度

第六部分：技术质量词（须适配上方【风格要求】，优先自然语言描述，避免照搬与风格冲突的固定词表）
- 通用质量描述：high detail, sharp focus, clean composition
- 风格匹配：anime→clean lineart / cel shading；watercolor→paper texture / soft washes；oil_painting→impasto brushstrokes；cinematic→cinematic lighting / film grain / 35mm；realistic→photorealistic
- 不要附加与风格冲突的电影感词（如 anime/watercolor 不加 film grain、35mm）
- 可酌情加入 rule of thirds、depth of field 等构图技法

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
                retries=retries,
                timeout=timeout,
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
