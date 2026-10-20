"""
Agnes 总导演节点
生成完整编号分镜脚本
输入：故事内容（小说章节或 漫剧剧本 均可），输出 5 秒/镜的编号分镜
"""
import requests
import re
import os
import time
import traceback
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort, format_chat_meta, sanitize_max_tokens


class AgnesDirectorMaster:
    """
    Agnes 总导演 v1
    使用 agnes-2.5-flash 生成完整分镜脚本
    """
    
    DESCRIPTION = "将故事内容（小说章节或漫剧剧本）生成为完整的编号分镜脚本，包含角色、场景、动作、情绪、台词等详细信息"

    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事内容（章节或剧本均可）...\n章节原文建议 3000-8000 字；也可连「Agnes 剧本生成」的漫剧剧本输出（场→镜精化）",
                    "tooltip": "故事内容：小说章节原文，或「Agnes 剧本生成」（漫剧剧本）的输出；将生成完整编号分镜脚本"
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
                    "max": 16000,
                    "step": 128,
                    "tooltip": "输出 token 预算：50 个分镜块需要大预算；思考模型（reasoning_effort≥medium）下建议拉满 16000 防空正文/截断"
                }),
            }
        }
        return inputs

    RETURN_TYPES = ("STRING",) * 55
    RETURN_NAMES = (
        "log_text",
        "scene_1", "scene_2", "scene_3", "scene_4", "scene_5",
        "scene_6", "scene_7", "scene_8", "scene_9", "scene_10",
        "scene_11", "scene_12", "scene_13", "scene_14", "scene_15",
        "scene_16", "scene_17", "scene_18", "scene_19", "scene_20",
        "scene_21", "scene_22", "scene_23", "scene_24", "scene_25",
        "scene_26", "scene_27", "scene_28", "scene_29", "scene_30",
        "scene_31", "scene_32", "scene_33", "scene_34", "scene_35",
        "scene_36", "scene_37", "scene_38", "scene_39", "scene_40",
        "scene_41", "scene_42", "scene_43", "scene_44", "scene_45",
        "scene_46", "scene_47", "scene_48", "scene_49", "scene_50",
        "chapter_text_out", "api_key_out", "base_url_out", "model_out",
    )
    RETURN_LABELS = (
        "处理日志",
        "分镜 1", "分镜 2", "分镜 3", "分镜 4", "分镜 5",
        "分镜 6", "分镜 7", "分镜 8", "分镜 9", "分镜 10",
        "分镜 11", "分镜 12", "分镜 13", "分镜 14", "分镜 15",
        "分镜 16", "分镜 17", "分镜 18", "分镜 19", "分镜 20",
        "分镜 21", "分镜 22", "分镜 23", "分镜 24", "分镜 25",
        "分镜 26", "分镜 27", "分镜 28", "分镜 29", "分镜 30",
        "分镜 31", "分镜 32", "分镜 33", "分镜 34", "分镜 35",
        "分镜 36", "分镜 37", "分镜 38", "分镜 39", "分镜 40",
        "分镜 41", "分镜 42", "分镜 43", "分镜 44", "分镜 45",
        "分镜 46", "分镜 47", "分镜 48", "分镜 49", "分镜 50",
        "原文本（透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）",
    )
    OUTPUT_TOOLTIPS = ("处理日志（分镜统计/响应元数据/空响应警示/错误详情）",) + (
        ("编号分镜脚本（5秒/段，含画面/对白/运镜，连接提示词生成节点）",) * 50
    ) + ("小说原文本（透传）", "API Key（透传）", "Base URL（透传）", "模型（透传）")
    FUNCTION = "split_scenes"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        outputs = {
            "log_text": "处理日志，包含成功/失败信息、响应元数据（finish_reason/token 消耗）、空响应警示和输出文件路径",
            "scene_1": "第 1 个分镜脚本，包含角色、场景、动作、情绪、台词",
            "scene_2": "第 2 个分镜脚本",
            "scene_3": "第 3 个分镜脚本",
            "scene_4": "第 4 个分镜脚本",
            "scene_5": "第 5 个分镜脚本",
        }
        for i in range(1, 51):
            outputs[f"scene_{i}"] = f"第 {i} 个分镜脚本（如果存在）"
        outputs["chapter_text_out"] = "原始小说章节文本（透传）"
        outputs["api_key_out"] = "API Key（透传）"
        outputs["base_url_out"] = "API 地址（透传）"
        outputs["model_out"] = "使用的模型名称（透传）"
        
        for key in outputs:
            if key in kwargs:
                extra[key] = {"description": outputs[key]}
        return extra

    def split_scenes(self, chapter_text="", base_url="", api_key="", model=CHAT_MODEL, reasoning_effort="auto", max_tokens=1024):
        max_tokens = sanitize_max_tokens(max_tokens, 1024)
        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            error_msg = "[错误] 缺少 API Key：请在节点内填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）"
            result = [error_msg] + [""] * 50 + [chapter_text, api_key, base_url, model]
            return tuple(result)
        print(f"\n{'='*60}")
        print(f"[Agnes 总导演 - {model}]")
        print(f"{'='*60}")

        prompt = f"""你是一位电影总导演。请通读以下故事内容（小说章节或漫剧剧本，均可），生成分镜脚本。

你的职责是规划故事情节和动作。人物外貌、服装、场景细节、天气光线由剧组秘书另行处理,你不需要写。

【分镜切分规则】

1. 粒度控制
   - 一个分镜 = 约5秒视频 = 2-4个连贯动作 + 1个固定场景
   - 只切有明确情节递进的部分: 角色位置变化、新角色登场、关键动作发生、情绪重大转折、对话得出新结论
   - 不切: 连续对话无实质进展、同一位置反复动作、角色无变化
   - 宁可段落稍长,不要切得过碎
   - 如果故事内容某段没有任何实质情节递进,直接跳过

2. 去重规则
   - 相邻分镜不能雷同,如果两个段落之间角色状态完全相同,跳过

3. 跳过无意义片段
   - 纯过渡性描述("他想了想"、"沉默片刻")如果没有推动情节,跳过

4. 场景切换检测【极其重要 - 严格遵循】
   触发条件(只有以下情况才切换场景):
   - 故事内容中明确写"走出X"、"进入X"、"来到X"、"回到X"、"离开X"
   - 故事内容中明确描述环境本质变化(天黑、天亮、下雨、下雪、起雾、暴风雪)

   不触发场景切换的情况:
   - 同一房间内走动、转头、起身、坐下、走到窗边
   - 视角变化、镜头感描述
   - 角色内心活动
   - 不确定是否切换时,默认不切换

5. 角色标注
   - 每个分镜标注出场角色: 角色名 (性别)
   - 新角色首次出场时标注,后续沿用
   - 如果角色未出场,不标注

6. 场景标注
   - 每个分镜标注场景名称 (如"客栈大厅"、"雪山小径")
   - 场景不变时写"同上"
   - 场景切换时必须给出新场景名称

【输出格式 - 严格遵循】

[SHOT 编号]
角色: 角色名 (性别)
场景: 场景名或"同上"
动作: 谁在哪做什么 (一句话,必须含具体动作词)
情绪: 角色情绪状态
台词 (如有): 角色说的话

示例:
[SHOT 1]
角色: 张三 (男)、李四 (女)
场景: 客栈大厅
动作: 张三从楼梯上走下来,李四在角落的桌子旁抬头看他
情绪: 李四惊讶,张三沉稳
台词: 李四:"你怎么来了?"

[SHOT 2]
角色: 张三 (男)、李四 (女)
场景: 同上
动作: 张三走到李四桌前,拉开椅子坐下
情绪: 李四疑惑
台词: 张三:"我来接你。"

... 继续直到内容结束,不限分镜数量

【故事内容（小说章节或漫剧剧本）】
{chapter_text}"""

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            content, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.2,
                max_tokens=max_tokens,
                reasoning_effort=normalize_reasoning_effort(reasoning_effort),
                return_meta=True,
            )

            shots = self._parse_shots(content or "")

            # 保存到输出目录
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "AgnesOutput")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            script_path = os.path.join(output_dir, f"director_master_agnes_{timestamp}.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(content or "")

            meta_line = format_chat_meta(meta, max_tokens)
            if not (content or "").strip():
                log = (f"⚠️ 空响应（{meta_line}）：API 返回 200 但正文为空，"
                       f"常见于思考模型预算耗尽——降低思考等级或调大 max_tokens 后重试（0 个分镜）")
            else:
                log = f"✅ Agnes 导演完成: {len(shots)} 个分镜\n· 响应元数据：{meta_line}\n📋 脚本: {script_path}"
            print(log)

            result = [log]
            for i in range(1, 51):
                result.append(shots.get(i, ""))
            result.append(chapter_text)
            result.append(api_key)
            result.append(base_url)
            result.append(model)

            return tuple(result)

        except Exception as e:
            tb = traceback.format_exc()
            error_msg = (f"❌ Agnes 导演失败（{type(e).__name__}）: {e}\n"
                         f"· 请求参数: model={model}；max_tokens={max_tokens}\n"
                         f"── 完整堆栈 ──\n{tb}")
            print(error_msg)
            result = [error_msg] + [""] * 50 + [chapter_text, api_key, base_url, model]
            return tuple(result)

    def _parse_shots(self, content):
        shots = {}
        blocks = re.split(r'\[SHOT\s+(\d+)\]', content)
        for i in range(1, len(blocks), 2):
            num = int(blocks[i])
            text = blocks[i+1].strip() if i+1 < len(blocks) else ""
            shots[num] = text
        return shots


NODE_CLASS_MAPPINGS = {"AgnesDirectorMaster": AgnesDirectorMaster}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesDirectorMaster": "🎬 Agnes 总导演"}
