"""
Agnes 资产提取节点
从故事内容（小说章节或 漫剧剧本 均可）中提取角色、场景、道具等资产信息
"""
import requests
import json
import re
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta, sanitize_max_tokens


class AgnesAssetExtractor:
    """使用 Agnes LLM 提取资产信息"""
    
    DESCRIPTION = "从故事内容（小说章节或漫剧剧本）中提取角色、场景、道具、服装、天气等资产信息，输出为 JSON 格式"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事内容（章节或剧本均可）...\n章节原文建议 3000-8000 字；也可连「Agnes 剧本生成」的漫剧剧本输出（提取该集要拍的资产）",
                    "tooltip": "故事内容：小说章节原文，或「Agnes 剧本生成」（漫剧剧本）的输出；生成 5 路资产 JSON"
                }),
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml），可动态调整"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key，从 https://platform.agnes-ai.com 获取"
                }),
                "model": (AVAILABLE_CHAT_MODELS, {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型（对话默认 agnes-2.5-flash；agnes-3.0-flash 适合 Agent/工具编排）"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
                }),
                "max_tokens": ("INT", {
                    "default": 1024,
                    "min": 512,
                    "max": 8192,
                    "step": 128,
                    "tooltip": "输出 token 预算：5 路资产 JSON 约需 1000-2000；思考模型（reasoning_effort≥medium）下建议调大（4000+）防空正文"
                }),
            },
            "optional": {}
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("characters_json", "locations_json", "props_json", "costumes_json", "weather_json", "log_text")
    RETURN_LABELS = (
        "角色信息 JSON",
        "场景信息 JSON",
        "道具列表 JSON",
        "服装信息 JSON",
        "天气信息 JSON",
        "处理日志",
    )
    OUTPUT_TOOLTIPS = (
        "角色列表 JSON（姓名/性别/年龄/外貌/性格，连接提示词节点增强角色一致性）",
        "场景列表 JSON（地点名称/环境描述/时代背景，连接提示词节点增强场景一致性）",
        "道具列表 JSON（重要物品名称+描述，可连 LLM 对话节点生成道具定妆文）",
        "服装列表 JSON（角色名+对应服装描述，可连 LLM 对话节点生成服装定妆文）",
        "天气/氛围 JSON（场景氛围补充，连接提示词节点增强一致性）",
        "处理日志（成功=各路统计+响应元数据；空响应=⚠️警示；JSON 解析失败=提示；异常=堆栈）",
    )
    FUNCTION = "extract"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        outputs = {
            "characters_json": "提取的角色列表，包含姓名、性别、年龄、外貌、性格等信息",
            "locations_json": "提取的场景列表，包含地点名称、环境描述、时代背景等",
            "props_json": "提取的道具列表，包含重要物品的名称和描述",
            "costumes_json": "提取的服装列表，包含角色名和对应的服装描述",
            "weather_json": "提取的天气信息，包含场景中的天气状况描述",
            "log_text": "处理日志（响应元数据/空响应警示/JSON 解析失败提示/异常堆栈）",
        }
        for key in outputs:
            if key in kwargs:
                extra[key] = {"description": outputs[key]}
        return extra

    def extract(self, chapter_text="", base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto", max_tokens=1024):
        max_tokens = sanitize_max_tokens(max_tokens, 1024)
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            return (err, "", "", "", "", "API Key 缺失。")
        print(f"\n{'='*50}")
        print(f"📋 Agnes 资产提取")
        print(f"{'='*50}")

        prompt = f"""你是一位专业的影视制片助理。请分析以下故事内容（小说章节或漫剧剧本，均可），提取以下资产信息：

【资产分类】
1. 角色：姓名、性别、年龄感、外貌特征、性格特点
2. 场景：地点名称、环境特点、时代背景
3. 道具：重要物品、服装细节
4. 服装：每个角色的主要服装描述
5. 天气：场景中的天气状况

【输出格式】
请以JSON格式输出，严格遵循以下结构：

{{
  "characters": [
    {{
      "name": "角色名",
      "gender": "男/女",
      "age": "年龄感",
      "appearance": "外貌描述",
      "personality": "性格特点"
    }}
  ],
  "locations": [
    {{
      "name": "场景名",
      "description": "环境描述",
      "era": "时代背景"
    }}
  ],
  "props": ["道具1", "道具2"],
  "costumes": [
    {{
      "character": "角色名",
      "description": "服装描述"
    }}
  ],
  "weather": ["天气1", "天气2"]
}}

【故事内容（小说章节或漫剧剧本）】
{chapter_text}"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.3,
                max_tokens=max_tokens,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )
            meta_line = format_chat_meta(meta, max_tokens)

            # 清理 markdown 代码块
            content = (raw or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

            if not content:
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级（none/low）或调大 max_tokens 后重试")
                print(f"[Agnes Asset] {log}")
                return ("", "", "", "", "", log)

            # 尝试解析 JSON
            try:
                data = json.loads(content)

                # 提取各字段
                characters = json.dumps(data.get("characters", []), ensure_ascii=False, indent=2)
                locations = json.dumps(data.get("locations", []), ensure_ascii=False, indent=2)
                props = json.dumps(data.get("props", []), ensure_ascii=False, indent=2)
                costumes = json.dumps(data.get("costumes", []), ensure_ascii=False, indent=2)
                weather = json.dumps(data.get("weather", []), ensure_ascii=False, indent=2)

                print(f"[Agnes Asset] 提取完成")
                print(f"  - 角色: {len(data.get('characters', []))} 个")
                print(f"  - 场景: {len(data.get('locations', []))} 个")
                print(f"  - 道具: {len(data.get('props', []))} 个")
                print(f"  - 服装: {len(data.get('costumes', []))} 套")
                print(f"  - 天气: {len(data.get('weather', []))} 种")

                log = (f"✅ 提取完成：角色 {len(data.get('characters', []))} / 场景 {len(data.get('locations', []))} / "
                       f"道具 {len(data.get('props', []))} / 服装 {len(data.get('costumes', []))} / 天气 {len(data.get('weather', []))}\n"
                       f"· 响应元数据：{meta_line}")
                return (characters, locations, props, costumes, weather, log)

            except json.JSONDecodeError:
                log = (f"⚠️ JSON 解析失败：原始文本（{len(content)} 字）已放入「角色信息 JSON」槽，其余槽为空\n"
                       f"· 响应元数据：{meta_line}\n"
                       f"· 建议：章节过短/模型跑题时重试，或换 agnes-2.5-flash + 思考 none")
                print(f"[Agnes Asset] JSON 解析失败，返回原始内容")
                print(log)
                return (content, "", "", "", "", log)

        except Exception as e:
            tb = traceback.format_exc()
            log = (f"❌ 资产提取失败（{type(e).__name__}）: {e}\n"
                   f"· 请求参数: model={model}；max_tokens={max_tokens}\n"
                   f"── 完整堆栈 ──\n{tb}")
            print(f"[Agnes Asset] 失败: {e}")
            return ("", "", "", "", "", log)


NODE_CLASS_MAPPINGS = {"AgnesAssetExtractor": AgnesAssetExtractor}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetExtractor": "📋 Agnes 资产提取"}
