# -*- coding: utf-8 -*-
"""
Agnes API Key 池配置节点（多端点 Key 池数据源）
==========================================
特殊节点（纯数据，零 API 调用）：把多组「Base URL + API Key」条目聚合成
一份池 JSON，输出给「Agnes 视频任务并发提交」节点（多端点顺序短路提交），
覆盖「国内 + 国外 Agnes 平台不同账号」场景（条目各自独立 Base URL + Key：
一端队列满 503，另一端绿窗可接任务）。

池 JSON 格式（pool_json 输出，一行，直连 并发提交 节点的 pool_json 输入）：
  [
    {"base_url": "https://api.agnes-ai.cn/v1", "api_key": "sk-…（国内）", "name": "国内"},
    {"base_url": "https://api.agnes-ai.com/v1", "api_key": "sk-…（国外）", "name": "国外"}
  ]
  - api_key 必填（缺 Key 条目自动跳过）；base_url 可空（=跟随全局配置）；
    name 可选（仅展示，供 池报告 辨识条目）
  - 重复 Key 自动去重（首个生效）

可选 include_global：启用时把当前全局 Key（API Key 配置节点 / 环境变量
AGNES_API_KEY / api_key_config.json / config.yaml，同 单提交 节点回退链）
作为末尾条目并入池（已在池中则不重复）——「单账号」场景免手贴，
退化为 1 条目池（行为等同 单提交 节点）。

七个输出（均 STRING，面板自上而下）：
  base_url:   池 JSON 数组中**随机抽 1 条**该条目的 Base URL（空=跟随全局）；
  full_key:   该随机条目的完整 API Key（未掩码，可直连单端点 提交/收取 节点的
              api_key 输入免再配——随机条目=池内任一账号）；
  masked_key: 该随机条目的掩码 Key（sk-…****…，供人工核对是哪一条）；
  pool_json:  规范化池 JSON（一行数组，直连 并发提交）；无有效条目="0" 标记
              （并发提交 节点见 "0" 零请求短路，同 单提交 "0" 标记族语义）；
  pool_count: 有效条目数（"0"=空池）；
  pool_report: 掩码清单（每条目一行：#i 名称 | 请求地址 | 掩码Key），供人工核对；
  status:     配置结果（ok / error 原因）。
"""

import json
import random
from typing import Tuple

from ..api import get_api_key, get_base_url, _mask_key
from ._output_docs import OutputDocsMixin

_POOL_JSON_EXAMPLE = (
    '[{"base_url": "https://api.agnes-ai.cn/v1", "api_key": "sk-…（国内）", "name": "国内"}, '
    '{"base_url": "https://api.agnes-ai.com/v1", "api_key": "sk-…（国外）", "name": "国外"}]'
)


def parse_pool_entries(raw) -> Tuple[list, str]:
    """池 JSON 解析（池配置 / 并发提交 节点共用）：接受 JSON 对象数组 /
    嵌套 JSON 字符串（防御，同 批量收取 _parse_entry）/ "0" 标记 / 空。

    返回 (entries, error)——error 非空时 entries=[]：
    entries 元素格式 {"base_url": str(可空), "api_key": str, "name": str(可空)}；
    缺 Key 条目跳过；重复 Key 去重（首个生效）。
    """
    raw = str(raw or "").strip()
    if not raw:
        return [], "API Key 池未连接（空输入）"
    if raw == "0":
        return [], "上游池 0 标记（池内无有效条目）"
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        return [], f"池 JSON 解析错误: {str(e)[:120]}"
    if isinstance(obj, str):  # 嵌套 JSON 字符串（防御）
        try:
            obj = json.loads(obj)
        except (json.JSONDecodeError, TypeError):
            return [], "池 JSON 嵌套字符串非合法 JSON"
    if not isinstance(obj, list):
        return [], '池 JSON 必须是对象数组: [{"base_url":…, "api_key":…}]'
    entries = []
    seen = set()
    for item in obj:
        if not isinstance(item, dict):
            continue
        key = str(item.get("api_key", "") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        entries.append({
            "base_url": str(item.get("base_url", "") or "").strip().rstrip("/"),
            "api_key": key,
            "name": str(item.get("name", "") or "").strip(),
        })
    if not entries:
        return [], "池内无有效条目（条目缺 API Key 或格式错误）"
    return entries, ""


class AgnesApiKeyPool(OutputDocsMixin):
    """Agnes API Key 池配置：多组 Base URL+Key 条目聚合成池 JSON（纯数据节点，零 API 调用），直连 视频任务并发提交；置顶 3 路随机条目输出（base_url/full_key/masked_key）。"""

    DESCRIPTION = "多端点 API Key 池配置（纯数据源，零 API 调用）：把多组「Base URL + API Key」条目（国内+国外不同账号等）聚合成一份池 JSON，直连「Agnes 视频任务并发提交」的池输入；池 JSON 格式=[{\"base_url\",\"api_key\",\"name\"}]（api_key 必填、base_url 可空=跟随全局、name 仅展示；重复 Key 自动去重）；可选 并入当前全局 Key 为末尾条目（单账号场景免手贴，退化为 1 条目池）；输出 7 路（面板自上而下）：置顶 3 路随机条目（池 JSON 数组中**随机抽 1 条**：base_url 该条目 Base URL + full_key 该条目完整 Key（未掩码，可直连单端点 提交/收取 的 api_key 输入免再配）+ masked_key 该条目掩码 Key（人工核对是哪条））+ pool_json（规范化池 JSON，无有效条目=0 标记）+ pool_count（条目数）+ pool_report（掩码清单，人工核对）+ status（配置结果）"

    CATEGORY = "Agnes Novel"
    FUNCTION = "generate"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("base_url", "full_key", "masked_key", "pool_json", "pool_count", "pool_report", "status")
    RETURN_LABELS = ("随机条目 Base URL", "随机条目完整 Key", "随机条目掩码 Key",
                    "池 JSON（输出）", "池条目数", "掩码清单", "配置状态")
    OUTPUT_DOCS = {
        "base_url": "池 JSON 数组中**随机抽 1 条**该条目的 Base URL（空串=该条目跟随全局配置）；每次运行重新随机，与 full_key/masked_key/pool_json 同批同条；无有效条目=空串",
        "full_key": "该随机条目的**完整 API Key（未掩码）**：直连单端点「Agnes 视频任务提交/收取」的 api_key 输入（免再配，随机条目=池内任一账号）；仅画布内传递，日志只显示掩码；无有效条目=空串",
        "masked_key": "该随机条目的掩码 Key（sk-…****…）：与 full_key 同条目，人工核对这次随机到的是池内哪一条；无有效条目=空串",
        "pool_json": "规范化池 JSON（一行数组，条目 {base_url, api_key, name}，缺 Key 条目已跳过、重复 Key 已去重）：直连「Agnes 视频任务并发提交」的池 JSON 输入；无有效条目=0 标记（下游并发提交 零请求短路，同 单提交 0 标记族语义）",
        "pool_count": "池内有效条目数（字符串）：0=空池（下游零请求短路）；1=单账号池（行为等同 单提交 节点）",
        "pool_report": "掩码清单（每条目一行：#i 名称 | 请求地址(空=全局) | sk-…****…）：人工核对池内容，Key 已掩码可安全显示",
        "status": "配置结果：ok: 池内 N 条（含并入全局说明 + 随机条目号）/ error: 原因（JSON 解析错误 / 无有效条目 / 池为空）",
    }

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pool_json": ("STRING", {
                    "label": "Key 池（JSON）",
                    "multiline": True,
                    "default": "",
                    "placeholder": _POOL_JSON_EXAMPLE,
                    "tooltip": "多组 Base URL+API Key 条目（JSON 对象数组，一行或多行均可）：api_key 必填（缺 Key 条目自动跳过）；base_url 可空=跟随全局；name 可选仅展示（供池报告辨识）；重复 Key 自动去重（国内 + 国外不同账号各填一组即可）",
                }),
            },
            "optional": {
                "include_global": ("BOOLEAN", {
                    "default": False,
                    "label_on": "是 - 并入全局 Key（末尾条目）",
                    "label_off": "否 - 只用粘贴池",
                    "tooltip": "启用时把当前全局 Key（API Key 配置节点 / 环境变量 AGNES_API_KEY / api_key_config.json / config.yaml，同 单提交 节点回退链）作为末尾条目并入池（已在池中则不重复，全局 Key 为空则跳过）：单账号场景免手贴，池退化为 1 条目（行为等同 单提交 节点）",
                }),
            },
        }

    def generate(self, pool_json: str = "", include_global: bool = False) -> Tuple:
        entries, err = parse_pool_entries(pool_json)
        global_note = ""
        if include_global:
            gkey = str(get_api_key() or "").strip()
            if not gkey:
                global_note = "（include_global 已启用但全局 Key 为空，未并入）"
            elif all(e["api_key"] != gkey for e in entries):
                entries.append({"base_url": str(get_base_url() or "").strip().rstrip("/"),
                                "api_key": gkey, "name": "全局（兜底）"})
                global_note = "（已并入全局 Key 1 条）"
            else:
                global_note = "（全局 Key 已在池中，未重复并入）"

        if entries:
            out = json.dumps(entries, ensure_ascii=False)
            count = str(len(entries))
            report = "\n".join(
                f"#{i} {e['name'] or '（未命名）'} | {e['base_url'] or '(全局)'} | {_mask_key(e['api_key'])}"
                for i, e in enumerate(entries, 1))
            # 随机抽 1 条置顶输出（base_url/full_key/masked_key 与 pool_json 同批同条；
            # full_key 未掩码仅画布内传递，日志只打掩码）
            pick = random.choice(entries)
            pick_i = entries.index(pick) + 1
            status = f"ok: 池内 {count} 条{global_note}（下游 并发提交 拿到有效池；随机抽 #{pick_i} 供置顶 3 路输出）"
            print(f"[Agnes API Key 池配置] 池内 {count} 条{global_note}："
                  + "; ".join(f"#{i} {e['base_url'] or '(全局)'} {_mask_key(e['api_key'])}"
                              for i, e in enumerate(entries, 1)))
            print(f"[Agnes API Key 池配置] 随机抽 #{pick_i} {pick['name'] or '（未命名）'}"
                  f" | {pick['base_url'] or '(全局)'} | {_mask_key(pick['api_key'])}"
                  f"（置顶 base_url/full_key/masked_key 输出该条）")
            return (pick["base_url"], pick["api_key"], _mask_key(pick["api_key"]),
                    out, count, report, status)

        # 无有效条目 → 0 标记（下游 并发提交 见 "0" 零请求短路；置顶 3 路随机输出=空串）
        reason = err or "池为空"
        status = f"error: {reason}{global_note}"
        print(f"[Agnes API Key 池配置] [错误] {status} → 输出 0 标记（下游 并发提交 零请求短路）")
        return ("", "", "", "0", "0", "", status)


NODE_CLASS_MAPPINGS = {"AgnesApiKeyPool": AgnesApiKeyPool}
NODE_DISPLAY_NAME_MAPPINGS = {"AgnesApiKeyPool": "🔑 Agnes API Key 池配置"}
