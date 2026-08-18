"""
Agnes 总导演节点
生成完整编号分镜脚本
"""
import requests
import re
import os
import time
from ..api import AgnesClient, get_api_key, BASE_URL, CHAT_MODEL


class AgnesDirectorMaster:
    """
    Agnes 总导演 v1
    使用 agnes-2.5-flash 生成完整分镜脚本
    """

    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "chapter_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入小说章节全文..."
                }),
                "api_key": ("STRING", {
                    "default": "sk-你的Key",
                    "placeholder": "Agnes API Key"
                }),
            },
            "optional": {
                "base_url": ("STRING", {"default": BASE_URL}),
                "model": ("STRING", {"default": CHAT_MODEL}),
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
    FUNCTION = "split_scenes"
    CATEGORY = "🎬 Agnes Novel"

    def split_scenes(self, chapter_text, api_key, base_url=BASE_URL, model=CHAT_MODEL):
        print(f"\n{'='*60}")
        print(f"[Agnes Director Master - {model}]")
        print(f"{'='*60}")

        prompt = f"""你是一位电影总导演。请通读以下小说章节,生成分镜脚本。

你的职责是规划故事情节和动作。人物外貌、服装、场景细节、天气光线由剧组秘书另行处理,你不需要写。

【分镜切分规则】

1. 粒度控制
   - 一个分镜 = 约5秒视频 = 2-4个连贯动作 + 1个固定场景
   - 只切有明确情节递进的部分: 角色位置变化、新角色登场、关键动作发生、情绪重大转折、对话得出新结论
   - 不切: 连续对话无实质进展、同一位置反复动作、角色无变化
   - 宁可段落稍长,不要切得过碎
   - 如果原文某段没有任何实质情节递进,直接跳过

2. 去重规则
   - 相邻分镜不能雷同,如果两个段落之间角色状态完全相同,跳过

3. 跳过无意义片段
   - 纯过渡性描述("他想了想"、"沉默片刻")如果没有推动情节,跳过

4. 场景切换检测【极其重要 - 严格遵循】
   触发条件(只有以下情况才切换场景):
   - 原文明确写"走出X"、"进入X"、"来到X"、"回到X"、"离开X"
   - 原文明确描述环境本质变化(天黑、天亮、下雨、下雪、起雾、暴风雪)

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

【小说章节】
{chapter_text}"""

        try:
            client = AgnesClient(api_key)
            content = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=0.2,
                max_tokens=12000,
            )

            shots = self._parse_shots(content)

            # 保存到输出目录
            output_dir = os.path.join(os.path.expanduser("~"), "Documents", "AgnesOutput")
            os.makedirs(output_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            script_path = os.path.join(output_dir, f"director_master_agnes_{timestamp}.txt")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(content)

            log = f"✅ Agnes 导演完成: {len(shots)} 个分镜\n📋 脚本: {script_path}"
            print(log)

            result = [log]
            for i in range(1, 51):
                result.append(shots[i] if i <= len(shots) else "")
            result.append(chapter_text)
            result.append(api_key)
            result.append(base_url)
            result.append(model)

            return tuple(result)

        except Exception as e:
            error_msg = f"❌ Agnes 导演失败: {e}"
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
