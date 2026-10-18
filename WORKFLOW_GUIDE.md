# 🎬 Agnes AI 小说推文完整工作流

基于 Agnes AI API 的端到端小说转动漫视频解决方案

## 📦 工作流文件

| 文件 | 说明 |
|------|------|
| `agnes-novel-to-movie.json` | 完整工作流（7个节点） |
| `agnes-novel-minimal.json` | 精简工作流（4个节点） |

---

## 🚀 快速开始

### 1. 安装插件

```powershell
# 解压到 ComfyUI custom_nodes 目录
Expand-Archive -Path "comfyui-agnes-novel.zip" -DestinationPath "你的ComfyUI路径\ComfyUI\custom_nodes\"
```

### 2. 重启 ComfyUI

### 3. 加载工作流

1. 打开 ComfyUI Web UI：http://localhost:8188
2. 点击 **Load** → 选择 `agnes-novel-to-movie.json`
3. 或拖拽 JSON 文件到工作区

---

## 📊 工作流节点说明

### 完整工作流 (agnes-novel-to-movie.json)

```
📖 小说文本输入
    ↓
┌─────────────────────────────────────┐
│  🎬 Agnes 场景切分                  │
│  将小说拆分为 5 秒/片的场景段落      │
│  输出：最多 50 个场景片段           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  🎬 Agnes 总导演                    │
│  生成完整编号分镜脚本               │
│  输出：角色、场景、动作、情绪、台词 │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  📋 Agnes 资产提取                  │
│  提取角色、场景、道具、服装、天气   │
│  输出：5 个 JSON 字符串             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  🎨 Agnes 分镜提示词生成            │
│  将分镜脚本转为英文生图提示词       │
│  输出：详细英文提示词               │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  🎨 Agnes 图像生成                  │
│  生成场景图像                       │
│  输出：IMAGE tensor + URL           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  🎬 Agnes 视频生成                  │
│  图生视频 / 文生视频                │
│  输出：视频文件路径 + video_id      │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  💾 SaveVideo                       │
│  保存最终视频                       │
│  输出：MP4 文件                     │
└─────────────────────────────────────┘
```

### 精简工作流 (agnes-novel-minimal.json)

```
📖 小说文本 → 🎬 场景切分 → 🎨 提示词生成 → 🎨 图像生成 → 🎬 视频生成 → 💾 保存
```

---

## ⚙️ 配置说明

### API Key 配置

在所有节点中输入 API Key（或配置环境变量）：
```powershell
$env:AGNES_API_KEY = "sk-你的Key"
```

### 默认配置

| 参数 | 值 |
|------|-----|
| Base URL | `https://api.agnes-ai.cn/v1` |
| 文本模型 | `agnes-2.5-flash`（可选 `agnes-3.0-flash` Agent 模型，支持 Thinking/工具调用） |
| 图像模型 | `agnes-image-2.5-flash`（档位 1K-4K + 比例；图生图/多图合成走 extra_body） |
| 视频模型 | `agnes-video-2.5-flash`（4-12 秒 / 720P / 首尾帧·参考图·音频参考） |
| 视频时长 | 5 秒（新接口 seconds 参数，4-12s） |
| 视频画质 | 1K |
| 宽高比 | 16:9 |

---

## 📁 输出文件

| 类型 | 位置 |
|------|------|
| 分镜脚本 | `%USERPROFILE%\Documents\AgnesOutput\` |
| 视频文件 | `ComfyUI/output/agnes_videos/` |

---

## 🔧 故障排除

### 视频生成超时
- 查看错误信息中的 `video_id`
- 尝试降低画质 (1K → 2K)
- 减少帧数 (121 → 81)

### API 认证失败
- 检查 API Key 是否正确
- 确认账户余额充足
- 访问 https://platform.agnes-ai.com 检查配额

### 图像生成质量差
- 优化提示词（添加质量词：masterpiece, best quality, 8k）
- 尝试不同的 aspect_ratio
- 使用 2K 画质

---

## 💰 成本估算 (Starter 档位 $4/月)

| 操作 | 单集成本 (20场景) |
|------|-------------------|
| LLM 调用 | ~0.10 USD |
| 图像生成 (20张) | ~0.20 USD |
| 视频生成 (20个) | ~2.00 USD |
| **总计** | **~2.30 USD** |

---

## 📞 支持

- **Agnes AI 平台**: https://platform.agnes-ai.com
- **文档**: https://agnes-ai.com/doc/overview
- **GitHub**: https://github.com/Lusensec/comfyui-agnes-novel

---

**版本**: 1.0.0  
**更新日期**: 2026-08-18  
**作者**: Lusensec
