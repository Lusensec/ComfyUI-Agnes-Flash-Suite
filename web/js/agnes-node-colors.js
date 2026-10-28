/**
 * Agnes Flash Suite —— Agnes 节点族按功能分类配色（"天生彩"）
 *
 * 背景：ComfyUI 服务端的 /object_info 不转发 Python 节点的 color/bgcolor 属性，
 * 节点颜色只能由前端决定（LiteGraph 渲染链：实例值 → 类静态值 → 全局默认灰 #333/#353535）。
 * 本扩展通过标准 beforeRegisterNodeDef 钩子，按功能分类给 Agnes* 节点类写入配色：
 *
 *   ┌ 配置类（琥珀）── API Key 配置 / 风格选择（不分级）
 *   │ 文本类·绿 ── 主绿：文本输入/解说剧本/漫剧剧本 ｜ 浅绿：场景切分/总导演/资产提取/LLM 对话
 *   │               ｜ 墨绿：分镜提示词/分镜提示词批量/文本拆分/资产提示词/资产提示词批量/三视图提示词/三视图提示词批量/字符串合并
 *   │ 图片类·蓝 ── 主蓝：图像生成/三视图批量生成/分镜图批量生成 ｜ 浅蓝：图生图 ｜ 深蓝：三视图生成/图像反推提示词/图像拼图
 *   └ 视频类·紫 ── 主紫：文生视频 ｜ 浅紫：关键帧生视频 ｜ 深紫：参考视频生成/视频任务提交/视频任务收取
 *
 * 同功能类用同一色系（一眼认出"这是文本/图片/视频节点"），类内再用主/浅/深三阶
 * 小幅度区分"主功能 / 次功能 / 工具与中间层"，避免全族单色无法分辨。
 *
 * 效果：新增节点一出现就带分类色；旧图里的节点在扩展 init 时补色；
 * 用户仍可右键「Set color」给单个节点换色（实例值优先，且会保存在工作流文件里）。
 *
 * 兼容：新 Vue 前端（comfyui-frontend-package，钩子签名 beforeRegisterNodeDef(nodeClass, nodeDef)）
 *       与旧 JS 前端（钩子签名 beforeRegisterNodeDef(nodeDef, nodeClass)），两种签名自适应。
 */
(function () {
    "use strict";

    // ── 功能分类配色板（想换颜色改这里；每类 main/light/deep 三阶，同色系微调） ──
    // 设计原则：标题/边框用亮色，主体(bgcColor)也要「明显带色系」——
    // 暖色（琥珀）主体压暗仍认得出色系；冷色（绿/蓝/紫）压暗会塌成黑，
    // 所以冷色主体必须提亮到"一眼是该色系"，整块节点才算"整体染色"。
    var PALETTE = {
        config: { color: "#e8a33d", bgcolor: "#3a2d16" },  // 配置·琥珀（不分级）
        text: {                                            // 文本·绿
            main:  { color: "#3fae62", bgcolor: "#2f5c44" },  // 主绿
            light: { color: "#6cc58c", bgcolor: "#447458" },  // 浅绿
            deep:  { color: "#2e8250", bgcolor: "#234a35" },  // 墨绿
        },
        image: {                                           // 图片·蓝（Agnes 品牌色）
            main:  { color: "#4c7dff", bgcolor: "#2f4c8a" },  // 主蓝
            light: { color: "#7ba0ff", bgcolor: "#4668b0" },  // 浅蓝
            deep:  { color: "#3159c2", bgcolor: "#24386b" },  // 深蓝
        },
        video: {                                           // 视频·紫
            main:  { color: "#a063d6", bgcolor: "#4a3670" },  // 主紫
            light: { color: "#c392ec", bgcolor: "#66528f" },  // 浅紫
            deep:  { color: "#7a44ad", bgcolor: "#382857" },  // 深紫
        },
    };

    // ── 节点 → 功能分类（与 nodes/__init__.py 的菜单分组一致） ──
    var CATEGORY_BY_NODE = {
        // 配置类
        "AgnesNovelAPIKeyConfig": "config",
        "AgnesStyleSelector": "config",
        // 文本类
        "AgnesNovelTextSource": "text",
        "AgnesScriptGenerator": "text",
        "AgnesScreenplayGenerator": "text",
        "AgnesSceneSplitter": "text",
        "AgnesDirectorMaster": "text",
        "AgnesAssetExtractor": "text",
        "AgnesScenePromptGenerator": "text",
        "AgnesScenePromptBatch": "text",
        "AgnesTextSplitter": "text",
        "AgnesAssetPromptGenerator": "text",
        "AgnesAssetPromptBatch": "text",
        "AgnesTurnaroundPromptGenerator": "text",
        "AgnesTurnaroundPromptBatch": "text",
        "AgnesVideoPromptGenerator": "text",
        "AgnesVideoPromptBatch": "text",
        "AgnesStringMerge": "text",
        "AgnesNovelLLMChat": "text",
        // 图片类
        "AgnesImageGen": "image",
        "AgnesNovelImageToImage": "image",
        "AgnesSubjectTurnaround": "image",
        "AgnesTurnaroundBatch": "image",
        "AgnesSceneImageBatch": "image",
        "AgnesNovelImageReverse": "image",
        "AgnesImageMosaic": "image",
        // 视频类
        "AgnesNovelTextToVideo": "video",
        "AgnesNovelImageToVideo": "video",
        "AgnesVideoReference": "video",
        "AgnesVideoTaskSubmit": "video",
        "AgnesVideoTaskCollect": "video",
        "AgnesVideoTaskCollectBatch": "video",
    };

    // ── 节点 → 类内色阶：main=主功能 / light=次功能 / deep=工具与中间层（未登记=main） ──
    var SHADE_BY_NODE = {
        // 文本类：绿
        "AgnesNovelTextSource": "main",
        "AgnesScriptGenerator": "main",
        "AgnesScreenplayGenerator": "main",
        "AgnesSceneSplitter": "light",
        "AgnesDirectorMaster": "light",
        "AgnesAssetExtractor": "light",
        "AgnesNovelLLMChat": "light",
        "AgnesScenePromptGenerator": "deep",
        "AgnesScenePromptBatch": "deep",
        "AgnesTextSplitter": "deep",
        "AgnesAssetPromptGenerator": "deep",
        "AgnesAssetPromptBatch": "deep",
        "AgnesTurnaroundPromptGenerator": "deep",
        "AgnesTurnaroundPromptBatch": "deep",
        "AgnesVideoPromptGenerator": "deep",
        "AgnesVideoPromptBatch": "deep",
        "AgnesStringMerge": "deep",
        // 图片类：蓝
        "AgnesImageGen": "main",
        "AgnesNovelImageToImage": "light",
        "AgnesSubjectTurnaround": "deep",
        "AgnesTurnaroundBatch": "main",
        "AgnesSceneImageBatch": "main",
        "AgnesNovelImageReverse": "deep",
        "AgnesImageMosaic": "deep",
        // 视频类：紫
        "AgnesNovelTextToVideo": "main",
        "AgnesNovelImageToVideo": "light",
        "AgnesVideoReference": "deep",
        "AgnesVideoTaskSubmit": "deep",
        "AgnesVideoTaskCollect": "deep",
        "AgnesVideoTaskCollectBatch": "main",  // 批量收取=主功能（同 三视图批量/分镜图批量 批量档）
    };

    function paletteOf(nodeName) {
        if (typeof nodeName !== "string" || nodeName.indexOf("Agnes") !== 0) return null;
        var cat = CATEGORY_BY_NODE[nodeName];
        if (!cat) return PALETTE.image.main;  // 新增的 Agnes 节点默认图片类主蓝
        var pal = PALETTE[cat];
        if (pal && pal.main) return pal[SHADE_BY_NODE[nodeName]] || pal.main;
        return pal;  // 配置类（单节点，无分级）
    }

    function paint(cls, def) {
        var pal = paletteOf(def && def.name);
        if (!pal) return;
        if (cls) {
            cls.color = pal.color;
            cls.bgcolor = pal.bgcolor;
        }
        if (def) {
            if (def.color === undefined) def.color = pal.color;
            if (def.bgcolor === undefined) def.bgcolor = pal.bgcolor;
        }
    }

    var extension = {
        name: "AgnesFlashSuite.NodeColors",

        // 节点定义注册时按类上色（新增节点从此天生带色）
        beforeRegisterNodeDef: function (arg1, arg2) {
            var cls = typeof arg1 === "function" ? arg1 : arg2;
            var def = typeof arg1 === "function" ? arg2 : arg1;
            paint(cls, def);
        },

        // 节点实例创建时兜底（实例值 undefined 时补类默认色）
        nodeCreated: function (node) {
            if (!node) return;
            var pal = paletteOf(node.comfyClass);
            if (!pal) return;
            if (node.color === undefined) node.color = pal.color;
            if (node.bgcolor === undefined) node.bgcolor = pal.bgcolor;
        },

        // 启动时对已存在的图（如刚加载的工作流）补色
        init: function (app) {
            try {
                var g = app && app.graph;
                if (!g || !g.nodes) return;
                for (var i = 0; i < g.nodes.length; i++) this.nodeCreated(g.nodes[i]);
                if (g.setDirty) g.setDirty(true, true);
            } catch (e) {
                /* 忽略：配色失败不影响节点功能 */
            }
        },
    };

    var api = null;
    if (typeof window !== "undefined" && window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app) {
        api = window.comfyAPI.app.app; // 新 Vue 前端
    } else if (typeof app !== "undefined") {
        api = app;                     // 旧 JS 前端（兼容）
    }

    if (api && api.registerExtension) {
        try {
            api.registerExtension(extension);
            console.log("[AgnesFlashSuite] Agnes 节点分类配色扩展已注册（配置=琥珀；文本=绿三阶；图片=蓝三阶；视频=紫三阶）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 配色扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
