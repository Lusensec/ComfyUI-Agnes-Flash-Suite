# 安装指南

## 方式 1：使用 comfyui-agnes-ai（推荐）

### 前提条件
确保已安装 [comfyui-agnes-ai](https://github.com/Lusensec/comfyui-agnes-ai) 插件。

### 安装步骤
```powershell
# 1. 进入 ComfyUI custom_nodes 目录
cd "你的ComfyUI路径\ComfyUI\custom_nodes"

# 2. 克隆本插件
git clone https://github.com/Lusensec/comfyui-agnes-novel.git

# 3. 重启 ComfyUI
```

## 方式 2：独立安装（无需 comfyui-agnes-ai）

### 安装步骤
```powershell
# 1. 下载 ZIP 包
# 解压到 ComfyUI/custom_nodes/

# 2. 或直接克隆
cd "你的ComfyUI路径\ComfyUI\custom_nodes"
git clone https://github.com/Lusensec/comfyui-agnes-novel.git

# 3. 重启 ComfyUI
```

## 配置 API Key

### 方式 1：环境变量
```powershell
$env:AGNES_API_KEY = "sk-你的Key"
# 或添加到系统环境变量
```

### 方式 2：配置文件
创建 `api_key_config.json`：
```json
{
  "api_key": "sk-你的Key"
}
```

### 方式 3：节点输入
在每个 Agnes 节点的 `api_key` 输入框中填入 Key。

## 验证安装

重启 ComfyUI 后，在节点列表中搜索 "Agnes"，应看到：

- 🎬 Agnes 场景切分
- 🎬 Agnes 总导演
- 📋 Agnes 资产提取
- 🎨 Agnes 提示词生成
- 🎨 Agnes 图像生成
- 🎬 Agnes 视频生成
- 📝 Agnes 剧本生成
