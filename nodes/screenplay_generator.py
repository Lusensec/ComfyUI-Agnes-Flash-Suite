"""
Agnes 剧本生成节点（漫剧短视频）
=================
使用 Agnes LLM 把故事大纲改写成「漫剧短视频分场剧本」：
核心钩子 + 分场四行结构（场景行/画面/对白/氛围），画面描述具象可视，
可直接接 场景切分 → 分镜提示词生成 → 图像生成 → 关键帧生视频 管线，
也可人工修改后作为漫剧/短剧的分镜脚本。

剧本类型按三维分类（三个独立参数，自由组合）：
  - tag（题材标签，讲什么）：逆袭爽文/甜宠CP/悬疑解谜/搞笑沙雕/热血动作/治愈日常/虐心催泪，
    另对齐「Agnes 风格选择」导演风格的 青春成长/家庭温馨/历史史诗/恐怖异灵/喜剧搞笑/科幻未来/都市末世/都市异能
  - emotion（情绪基调，观众什么感受）：爽/暖/爆笑/热血/紧张/泪
  - rhythm（节奏，多快）：快节奏/中速/慢热（同时决定每场秒数与钩子密度）

题材输入：tag（STRING 输入口）——可直接手输题材名，或连「Agnes 风格选择」的 导演风格 输出
（连线后覆盖手输值）；留空=默认「逆袭爽文」；未知题材名按通用描述兜底，不报错。

输出 2 路：
  - script   漫剧剧本
  - log_text 响应日志（成功=参数/场次/响应元数据 finish_reason+token 消耗+思考 token 明细/耗时/
             原始响应摘录；空响应=⚠️ 警示+三条排查建议；失败=异常类型/完整堆栈/请求参数/
             请求地址，覆盖 API Key 缺失、网络、HTTP 错误、响应格式异常全部报错情况）

与「Agnes 解说剧本生成（AgnesScriptGenerator）」的区别：
  - 解说剧本生成 = 口播解说稿（配音轨，对观众的叙述腔）
  - 本节点       = 分场剧本（画面+对白+氛围，漫剧结构）
"""

import re
import time
import traceback
from ..api import AgnesClient, get_api_key, get_base_url, BASE_URL, CHAT_MODEL, AVAILABLE_CHAT_MODELS, REASONING_EFFORTS, normalize_reasoning_effort


class AgnesScreenplayGenerator:
    """使用 Agnes LLM 生成漫剧短视频分场剧本（题材×情绪×节奏三维定制）"""

    DESCRIPTION = "根据故事大纲生成漫剧短视频分场剧本（核心钩子+画面/对白/氛围），题材标签×情绪基调×节奏三维定制"

    TAG_MAP = {
        "逆袭爽文": "逆袭爽文：小人物翻盘、打脸反转、憋屈到痛快",
        "甜宠CP": "甜宠CP：恋爱/CP 互动、撒糖名场面、心动细节",
        "悬疑解谜": "悬疑解谜：谜团线索、层层反转、钩子悬念",
        "搞笑沙雕": "搞笑沙雕：沙雕笑点、梗密度高、名场面整活",
        "热血动作": "热血动作：打斗/闯关、成长线、高燃爆发",
        "治愈日常": "治愈日常：市井烟火、小确幸、萌宠/陪伴线、温情细节",
        "虐心催泪": "虐心催泪：亲情/命运拉扯、虐点精准、共情爆发",
        # 与「Agnes 风格选择」导演风格对齐（外部连线进来的题材名由此表提供导向文案）
        "青春成长": "青春成长：少年心境、成长蜕变与自我寻找，希望感收尾",
        "家庭温馨": "家庭温馨：亲情日常、暖系细节与陪伴感，治愈收束",
        "历史史诗": "历史史诗：宏大场面、命运抉择与厚重叙事",
        "恐怖异灵": "恐怖异灵：灵异悬疑、氛围压迫与伏笔突现",
        "喜剧搞笑": "喜剧搞笑：笑点密集、角色梗多、包袱节奏快",
        "科幻未来": "科幻未来：未来世界观、科技美学与人类命题",
        "都市末世": "都市末世：末世求生、资源稀缺与人性考验",
        "都市异能": "都市异能：现代都市+超能力体系、能力成长与爽点名场面",
    }

    EMOTION_MAP = {
        "爽": "爽感：主角赢、解气翻身，观众痛快解压",
        "暖": "温暖：治愈暖心，观众心里一暖",
        "爆笑": "爆笑：笑点密集，观众绷不住",
        "热血": "热血：心跳加速的燃，观众被点燃",
        "紧张": "紧张：屏息揪心，观众不敢快进",
        "泪": "泪点：共情/心酸/感动，观众掉泪",
    }

    RHYTHM_MAP = {
        "快节奏": ("高密度快切：钩子/笑点/爽点每 1–2 场必须出现一次，对白短促，不铺垫不拖沓", 5, 8, 6),
        "中速": ("标准漫剧节奏：每 3–4 场一个重点，起承转合各有一次爆发", 8, 12, 9),
        "慢热": ("慢烧沉浸：细节与情绪铺垫优先，钩子只放全剧 3 个转折点，对白允许带情绪", 12, 15, 13),
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "story_outline": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "输入故事大纲或章节摘要...",
                    "tooltip": "故事大纲，用于生成漫剧剧本"
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
                "tag": ("STRING", {
                    "default": "逆袭爽文",
                    "placeholder": "题材名（可手输，也可连线）：逆袭爽文/甜宠CP/悬疑解谜/搞笑沙雕/热血动作/治愈日常/虐心催泪/青春成长/家庭温馨/历史史诗/恐怖异灵/喜剧搞笑/科幻未来/都市末世/都市异能",
                    "tooltip": "题材标签（讲什么）：手输题材名，或直接连「Agnes 风格选择」的 导演风格 输出（连线后覆盖手输值）；留空=默认逆袭爽文；未知题材名自动按通用描述兜底，不会报错"
                }),
                "emotion": (list(cls.EMOTION_MAP.keys()), {
                    "default": "爽",
                    "tooltip": "情绪基调（观众什么感受）：爽/暖/爆笑/热血/紧张/泪"
                }),
                "rhythm": (list(cls.RHYTHM_MAP.keys()), {
                    "default": "快节奏",
                    "tooltip": "节奏（多快）：快节奏（钩子每 1–2 场）/ 中速（每 3–4 场）/ 慢热（只留 3 个转折点钩子）"
                }),
                "target_duration": ("INT", {
                    "default": 180,
                    "min": 60,
                    "max": 600,
                    "tooltip": "目标总时长（秒），场次按节奏估算（快≈6s/场、中≈9s/场、慢≈13s/场）"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.8,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "tooltip": "生成温度，越高越有创意，越低越稳定"
                }),
                "reasoning_effort": (list(REASONING_EFFORTS), {
                    "default": "auto",
                    "tooltip": "思考等级 reasoning_effort（Agnes 2.5/3.0 文本模型）：auto=跟随模型默认 / none=完全关闭思考 / low / medium / high / max；2.0 旧模型不生效"
                }),
            },
            "optional": {
                "characters": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "每行一个角色：名字 + 一句人设，如「团团：胖橘猫，傲娇贪吃」「张大婶：热心洗衣大婶」",
                    "tooltip": "可选：角色列表（每行一个，名字+一句人设），让剧本对白/动作保持角色一致"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("script", "log_text")
    RETURN_LABELS = ("漫剧剧本", "响应日志")
    OUTPUT_TOOLTIPS = (
        "漫剧短视频分场剧本（核心钩子+分场四行结构：场景行/画面/对白/氛围）；可接 总导演/资产提取/分镜提示词生成 继续管线，或接 SaveText 存档",
        "响应/诊断日志：成功=三维参数+场次估算+模型参数+耗时+原始响应摘录；失败=异常类型/完整堆栈/请求参数/请求地址/解决建议，覆盖 API Key 缺失、网络超时、HTTP 错误、响应格式异常等全部报错情况，直接在节点上查看",
    )
    FUNCTION = "generate"
    CATEGORY = "Agnes Novel"
    OUTPUT_NODE = True

    @classmethod
    def get_extra_output_methods(cls):
        return ["get_extra_pnginfo"]

    def get_extra_pnginfo(self, **kwargs):
        extra = {}
        if "script" in kwargs:
            extra["script"] = {
                "description": "漫剧短视频分场剧本，含核心钩子与分场场景行/画面/对白/氛围结构"
            }
        if "log_text" in kwargs:
            extra["log_text"] = {
                "description": "响应日志（参数/耗时/原始响应摘录 或 异常诊断）"
            }
        return extra

    def generate(self, story_outline="", base_url="", api_key="", tag="逆袭爽文", emotion="爽", rhythm="快节奏", target_duration=180, temperature=0.8, model=CHAT_MODEL, reasoning_effort="auto", characters=""):
        t0 = time.time()
        eff_re = normalize_reasoning_effort(reasoning_effort)

        # tag 为 STRING 输入：可手输题材名、可连「Agnes 风格选择」导演风格、可留空用默认；
        # 未知题材名按通用描述兜底（KeyError 防护）
        tag_raw = (tag or "").strip()
        tag = tag_raw or "逆袭爽文"

        # 三轴兜底：未知情绪/节奏不崩（KeyError 防护 + 通用描述）
        emotion = (emotion or "").strip() or "爽"
        rhythm = (rhythm or "").strip() or "中速"
        tag_desc = self.TAG_MAP.get(tag, f"{tag}：以「{tag}」为题材方向创作")
        emotion_desc = self.EMOTION_MAP.get(emotion, f"{emotion}（以该情绪基调创作）")
        rhythm_req, sec_lo, sec_hi, sec_avg = self.RHYTHM_MAP.get(rhythm, self.RHYTHM_MAP["中速"])
        target_scenes = max(3, round(target_duration / sec_avg))
        characters_block = f"\n角色设定（剧本中的对白/动作请保持这些角色一致）：\n{characters}\n" if characters.strip() else ""

        if not api_key.strip():
            api_key = get_api_key()
        if not api_key.strip():
            err = ("❌ 未发起 API 请求（配置缺失）：缺少 API Key。\n"
                   "· 节点内 api_key 为空，且全局配置（「Agnes API Key 配置」节点 / 环境变量 AGNES_API_KEY / config.yaml）均未提供\n"
                   "· 解决：在本节点 api_key 栏填写，或在「Agnes API Key 配置」节点配置（免费 Key：https://platform.agnes-ai.com/）")
            print(f"[Agnes 漫剧剧本] {err}")
            return ("[错误] 缺少 API Key（详情见「响应日志」输出）", err)

        prompt = f"""你是一位专业的漫剧短视频编剧，擅长把故事大纲改写成适合 AI 漫剧（动态漫画短剧）的分场剧本：节奏快、画面感强、每场都能直接转成画面与镜头。请根据以下故事大纲创作剧本。

剧本定制（三维）：
- 题材标签：{tag_desc}
- 情绪基调：{emotion_desc}
- 节奏：{rhythm_req}

故事大纲：
{story_outline}
{characters_block}
【剧本格式】
1. 剧本第一行写「核心钩子」：一句话点出全剧最抓人的悬念/爽点/情绪点
2. 然后分场写作，每场四行、各占一行：
   场景一：DAY 河畔石池
   画面：（景别+镜头内容+角色动作表情，如「全景：薄雾小镇河边，团团蹲在石池边拨水够银鲤」）
   对白：（格式「角色名：台词」，可多句；无台词写「对白：无」）
   氛围：（一句情绪/音效设计，如「水花声+远处市井人声」）
3. 场景编号用中文数字（场景一、场景二……），场景行写 时间(DAY/NIGHT)+地点
4. 每场 {sec_lo}–{sec_hi} 秒，全剧共 {target_scenes} 场左右，总时长约 {target_duration} 秒

【节奏要求】
- {rhythm_req}
- 全剧情绪主色调：{emotion_desc.split("：", 1)[0]}（关键场可短暂偏离制造反差，但落点要回到主色调）

【结构与写法】
- 钩子开场（前 3 场必须抓人）→ 冲突发展（反转/升级）→ 高潮收束 → 结尾留钩（为下一集埋悬念）
- 对白短促、有角色感，可设计口头禅；动作描写具象可视（不写「心里难受」，写「手指攥紧衣角，指节发白」）

【禁止事项】
- 不要解说腔：禁止「你想想」「你看」「别划走」等对观众的口播话术
- 不要用【】等标记符号，不要「第一、第二」列表式结构
- 不要总结性废话，直接输出剧本："""

        print(f"[Agnes 漫剧剧本] {tag}×{emotion}×{rhythm}：生成分场剧本（约 {target_scenes} 场 / {target_duration} 秒），思考等级={eff_re or '默认'}...")

        try:
            client = AgnesClient(api_key, base_url=base_url.strip() or None)
            raw, meta = client.chat(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                reasoning_effort=eff_re,
                return_meta=True,
            )

            # 清理（与 解说剧本生成 一致的兜底）
            script = re.sub(r'【[^】]*】', '', raw)
            script = re.sub(r'\[[^\]]*\]', '', script)
            script = re.sub(r'\n{3,}', '\n\n', script)
            script = script.strip()

            elapsed = time.time() - t0
            usage = meta.get("usage") or {}
            tag_src = f"tag 输入 = {tag_raw}" if tag_raw else "tag 留空，用默认「逆袭爽文」"
            resp_meta_line = (f"· 响应元数据：finish_reason={meta.get('finish_reason')}；"
                              f"completion_tokens={usage.get('completion_tokens')}（上限=模型默认）"
                              + (f"，其中思考 {meta.get('reasoning_tokens')} tokens" if meta.get("reasoning_tokens") else "")
                              + "；total_tokens=" + str(usage.get("total_tokens")))
            raw_excerpt = raw[:400] + ("..." if len(raw) > 400 else "")
            if not raw:
                warn = ("⚠️ 空响应（API 返回 200 但正文为空）：常见于思考型模型预算耗尽"
                        "（finish_reason=length 时，思考链占满输出上限、正文 0 token）。"
                        "建议：① 降低思考等级（medium→low/none）② 换 agnes-2.5-flash "
                        "③ 减场次（中速节奏或缩短 target_duration）后重试")
                print(f"[Agnes 漫剧剧本] {warn.split('：')[0]}")
                log = (f"⚠️ 空响应（未生成剧本）（耗时 {elapsed:.1f} 秒）\n"
                       f"· 三维参数：{tag} × {emotion} × {rhythm}（{tag_src}）\n"
                       f"{resp_meta_line}\n"
                       f"· 模型：{model}（reasoning_effort={eff_re or '默认'}，temperature={temperature}）\n"
                       f"· 请求地址：{client.base_url}\n"
                       f"── 诊断 ──\n{warn}")
                return ("", log)

            log = (f"✅ 生成成功（耗时 {elapsed:.1f} 秒）\n"
                   f"· 三维参数：{tag} × {emotion} × {rhythm}（{tag_src}）\n"
                   f"· 场次估算：约 {target_scenes} 场 / 目标 {target_duration} 秒（{sec_lo}–{sec_hi} 秒/场）\n"
                   f"{resp_meta_line}\n"
                   f"· 模型：{model}（reasoning_effort={eff_re or '默认'}，temperature={temperature}）\n"
                   f"· 请求地址：{client.base_url}\n"
                   f"· 原始响应 {len(raw)} 字 → 清理后 {len(script)} 字\n"
                   f"── 原始响应（前 400 字）──\n{raw_excerpt}")
            print(f"[Agnes Screenplay] Generated {len(script)} chars")
            return (script, log)

        except Exception as e:
            base_disp = base_url.strip() or ("（跟随全局，当前 " + get_base_url() + "）")
            log = (f"❌ API 调用失败（{type(e).__name__}）\n"
                   f"· 异常信息：{e}\n"
                   f"· 请求参数：tag={tag} × emotion={emotion} × rhythm={rhythm}；model={model}；reasoning_effort={eff_re or '默认'}；temperature={temperature}\n"
                   f"· 请求地址：{base_disp}\n"
                   f"· 提示词 {len(prompt)} 字 / 大纲 {len(story_outline)} 字 / 角色设定 {len(characters)} 字\n"
                   f"· 已耗时 {time.time() - t0:.1f} 秒（含客户端自动重试等待）\n"
                   f"── 完整堆栈 ──\n{traceback.format_exc()}")
            print(f"[Agnes Screenplay] Failed: {type(e).__name__}: {e}")
            return (f"[Error] {type(e).__name__}: {e}", log)


NODE_CLASS_MAPPINGS = {"AgnesScreenplayGenerator": AgnesScreenplayGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesScreenplayGenerator": "🎭 Agnes 剧本生成"}
