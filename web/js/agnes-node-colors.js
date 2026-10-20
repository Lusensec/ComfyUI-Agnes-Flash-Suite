/**
 * Agnes Flash Suite —— Agnes 节点族按功能分类配色（"天生彩"）
 *
 * 背景：ComfyUI 服务端的 /object_info 不转发 Python 节点的 color/bgcolor 属性，
 * 节点颜色只能由前端决定（LiteGraph 渲染链：实例值 → 类静态值 → 全局默认灰 #333/#353535）。
 * 本扩展通过标准 beforeRegisterNodeDef 钩子，按功能分类给 Agnes* 节点类写入配色：
 *
 *   ┌ 配置类（琥珀）── API Key 配置
 *   │ 文本类（绿）  ── 文本输入 / 剧本生成 / 场景切分 / 总导演 / 资产提取 / 分镜提示词 /
 *   │                   文本拆分 / 资产提示词 / 三视图提示词 / 字符串合并 / LLM 对话
 *   │ 图片类（蓝）  ── 图像生成 / 图生图 / 三视图生成 / 图像反推提示词
 *   └ 视频类（紫）  ── 文生视频 / 关键帧生视频 / 参考视频生成
 *
 * 效果：新增节点一出现就带分类色；旧图里的节点在扩展 init 时补色；
 * 用户仍可右键「Set color」给单个节点换色（实例值优先，且会保存在工作流文件里）。
 *
 * 兼容：新 Vue 前端（comfyui-frontend-package，钩子签名 beforeRegisterNodeDef(nodeClass, nodeDef)）
 *       与旧 JS 前端（钩子签名 beforeRegisterNodeDef(nodeDef, nodeClass)），两种签名自适应。
 */
(function () {
    "use strict";

    // ── 功能分类配色板（想换颜色改这里） ─────────────────
    var PALETTE = {
        config: { color: "#e8a33d", bgcolor: "#3a2d16" },  // 配置·琥珀
        text:   { color: "#3fae62", bgcolor: "#1d3a28" },  // 文本·绿
        image:  { color: "#4c7dff", bgcolor: "#1e2f52" },  // 图片·蓝（Agnes 品牌色）
        video:  { color: "#a063d6", bgcolor: "#2b1d42" },  // 视频·紫
    };

    // ── 节点 → 功能分类（与 nodes/__init__.py 的菜单分组一致） ──
    var CATEGORY_BY_NODE = {
        // 配置类
        "AgnesNovelAPIKeyConfig": "config",
        // 文本类
        "AgnesNovelTextSource": "text",
        "AgnesScriptGenerator": "text",
        "AgnesSceneSplitter": "text",
        "AgnesDirectorMaster": "text",
        "AgnesAssetExtractor": "text",
        "AgnesScenePromptGenerator": "text",
        "AgnesTextSplitter": "text",
        "AgnesAssetPromptGenerator": "text",
        "AgnesTurnaroundPromptGenerator": "text",
        "AgnesStringMerge": "text",
        "AgnesNovelLLMChat": "text",
        // 图片类
        "AgnesImageGen": "image",
        "AgnesNovelImageToImage": "image",
        "AgnesSubjectTurnaround": "image",
        "AgnesNovelImageReverse": "image",
        // 视频类
        "AgnesNovelTextToVideo": "video",
        "AgnesNovelImageToVideo": "video",
        "AgnesVideoReference": "video",
    };

    function paletteOf(nodeName) {
        if (typeof nodeName !== "string" || nodeName.indexOf("Agnes") !== 0) return null;
        var cat = CATEGORY_BY_NODE[nodeName];
        return PALETTE[cat] || PALETTE.image;  // 新增的 Agnes 节点默认归图片类蓝色
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
            console.log("[AgnesFlashSuite] Agnes 节点分类配色扩展已注册（配置=琥珀 文本=绿 图片=蓝 视频=紫）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 配色扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
