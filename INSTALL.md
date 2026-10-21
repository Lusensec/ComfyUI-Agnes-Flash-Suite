# 安装指南

本套件**自包含**（API 客户端内置于 `api/` 模块），**无需**安装 comfyui-agnes-ai 或任何其他 Agnes 相关插件。

## 方式 1：Git 克隆（推荐）

```powershell
# 1. 进入 ComfyUI custom_nodes 目录
cd "你的ComfyUI路径\ComfyUI\custom_nodes"

# 2. 克隆本插件
git clone https://github.com/Lusensec/Comfyui-Agnes-Flash-Suite.git

# 3. 重启 ComfyUI
```

## 方式 2：ZIP 下载

1. 下载 release ZIP（或代码 ZIP）并解压
2. 解压到 `ComfyUI/custom_nodes/`，目录名保持为 `Comfyui-Agnes-Flash-Suite`
3. 重启 ComfyUI

## 依赖

ComfyUI 本体已提供全部第三方库（requests / PyYAML / Pillow / numpy / torch），无需额外 pip 安装；Python 3.10+。

## 配置 API Key

三种方式（可混用，优先级从高到低）：

### 方式 1：节点输入
在节点的 `api_key` 输入框中直接填写 Key（最高优先级）。

### 方式 2：环境变量
```powershell
$env:AGNES_API_KEY = "sk-你的Key"
# 或添加到系统环境变量
```

### 方式 3：配置文件
「🔑 Agnes API Key 配置」节点会写入 `api_key_config.json` 缓存：
```json
{
  "api_key": "sk-你的Key"
}
```

也可在内置 `config.yaml` 的 `api_key` 字段填写（优先级最低）。

## 验证安装

重启 ComfyUI 后，控制台应出现：

```
[AgnesNovel] 已加载 23 个节点
```

在节点列表中搜索 "Agnes"，应看到 23 个节点（按功能分类配色）：

- 🔑 Agnes API Key 配置 / 🪄 Agnes 风格选择 / 📥 Agnes 文本输入
- 📝 Agnes 解说剧本生成 / 🎭 Agnes 剧本生成 / 🎬 Agnes 场景切分 / 🎬 Agnes 总导演
- 📋 Agnes 资产提取 / ✂️ Agnes 文本拆分 / 🖌️ Agnes 资产提示词生成
- ✍️ Agnes 三视图提示词生成 / 🎨 Agnes 分镜提示词生成 / 🔗 Agnes 字符串合并 / 💬 Agnes LLM 对话
- 🎨 Agnes 图像生成 / 🖼️ Agnes 图生图 / 📐 Agnes 三视图生成 / 📐 Agnes 三视图批量生成 / 🔍 Agnes 图像反推提示词
- 🎞️ Agnes 文生视频 / 🎬 Agnes 关键帧生视频 / 🎞️ Agnes 参考视频生成
- 📄 Agnes 字符串展示（展示类，独立玫瑰红配色）
