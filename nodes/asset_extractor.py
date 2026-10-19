"""
Agnes 资产提取节点
从小说文本中提取角色、场景、道具等资产信息
"""
import requests
import json
import re
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL


class AgnesAssetExtractor:
    """使用 Agnes LLM 提取资产信息"""
    
    DESCRIPTION = "从小说章节中提取角色、场景、道具、服装、天气等资产信息，输出为 JSON 格式"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入小说章节全文...",
                    "tooltip": "待处理的小说章节文本，建议 3000-8000 字"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "placeholder": "sk-xxxxxxxx",
                    "tooltip": "Agnes AI API Key，从 https://platform.agnes-ai.com 获取"
                }),
            },
            "optional": {
                "base_url": ("STRING", {
                    "default": "",
                    "placeholder": "https://api.agnes-ai.cn/v1",
                    "tooltip": "请求地址 Base URL：留空=跟随全局（API Key 配置节点/环境变量 AGNES_API_BASE_URL/config.yaml）"
                }),
                "model": ("STRING", {
                    "default": CHAT_MODEL,
                    "tooltip": "文本生成模型，推荐使用 agnes-2.5-flash"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("characters_json", "locations_json", "props_json", "costumes_json", "weather_json")
    RETURN_LABELS = (
        "角色信息 JSON",
        "场景信息 JSON",
        "道具列表 JSON",
        "服装信息 JSON",
        "天气信息 JSON"
    )
    OUTPUT_TOOLTIPS = (
        "角色列表 JSON（姓名/性别/年龄/外貌/性格，连接资产拆分器或提示词节点）",
        "场景列表 JSON（地点名称/环境描述/时代背景，连接资产拆分器或提示词节点）",
        "道具列表 JSON（重要物品名称+描述，连接资产拆分器）",
        "服装列表 JSON（角色名+对应服装描述，连接资产拆分器）",
        "天气/氛围 JSON（场景氛围补充，连接提示词节点增强一致性）",
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
        }
        for key in outputs:
            if key in kwargs:
                extra[key] = {"description": outputs[key]}
        return extra

    def extract(self, chapter_text, api_key, base_url="", model=CHAT_MODEL):
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = "[Error: API key is required. Get a free key at https://platform.agnes-ai.com/]"
            return (err, "", "", "", "")
        print(f"\n{'='*50}")
        print(f"📋 Agnes 资产提取")
        print(f"{'='*50}")

        prompt = f"""你是一位专业的影视制片助理。请分析以下小说章节，提取以下资产信息：

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

【小说章节】
{chapter_text}"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.3,
                max_tokens=3000,
            )

            # 清理 markdown 代码块
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]

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

                return (characters, locations, props, costumes, weather)

            except json.JSONDecodeError:
                print(f"[Agnes Asset] JSON 解析失败，返回原始内容")
                return (content, "", "", "", "")

        except Exception as e:
            print(f"[Agnes Asset] 失败: {e}")
            return ("", "", "", "", "")


NODE_CLASS_MAPPINGS = {"AgnesAssetExtractor": AgnesAssetExtractor}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesAssetExtractor": "📋 Agnes 资产提取"}
