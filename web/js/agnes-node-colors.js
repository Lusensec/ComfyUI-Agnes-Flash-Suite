/**
 * Agnes Flash Suite —— Agnes 节点族统一配色（"天生彩"）
 *
 * 背景：ComfyUI 服务端的 /object_info 不转发 Python 节点的 color/bgcolor 属性，
 * 节点颜色只能由前端决定（LiteGraph 渲染链：实例值 → 类静态值 → 全局默认灰 #333/#353535）。
 * 本扩展通过标准 beforeRegisterNodeDef 钩子，给所有 Agnes* 节点类写入 Agnes 蓝：
 *   - color   (标题栏/强调)  #4c7dff
 *   - bgcolor (节点主体)     #1e2f52
 * 效果：新增节点一出现就是 Agnes 蓝；旧图里的节点在扩展 init 时补色；
 * 用户仍可右键「Set color」给单个节点换色（实例值优先，且会保存在工作流文件里）。
 *
 * 兼容：新 Vue 前端（comfyui-frontend-package，钩子签名 beforeRegisterNodeDef(nodeClass, nodeDef)）
 *       与旧 JS 前端（钩子签名 beforeRegisterNodeDef(nodeDef, nodeClass)），两种签名自适应。
 */
(function () {
    "use strict";

    // ── Agnes 蓝配色（想换颜色改这两行） ─────────────────
    var AGNES_COLOR = "#4c7dff";   // 标题栏 / 强调色
    var AGNES_BGCOLOR = "#1e2f52";  // 节点主体

    function isAgnes(name) {
        return typeof name === "string" && name.indexOf("Agnes") === 0;
    }

    function paint(cls, def) {
        if (cls) {
            cls.color = AGNES_COLOR;
            cls.bgcolor = AGNES_BGCOLOR;
        }
        if (def) {
            if (def.color === undefined) def.color = AGNES_COLOR;
            if (def.bgcolor === undefined) def.bgcolor = AGNES_BGCOLOR;
        }
    }

    var extension = {
        name: "AgnesFlashSuite.NodeColors",

        // 节点定义注册时按类上色（新增节点从此天生带色）
        beforeRegisterNodeDef: function (arg1, arg2) {
            var cls = typeof arg1 === "function" ? arg1 : arg2;
            var def = typeof arg1 === "function" ? arg2 : arg1;
            if (!def || !isAgnes(def.name)) return;
            paint(cls, def);
        },

        // 节点实例创建时兜底（实例值 undefined 时补类默认色）
        nodeCreated: function (node) {
            if (!node || !isAgnes(node.comfyClass)) return;
            if (node.color === undefined) node.color = AGNES_COLOR;
            if (node.bgcolor === undefined) node.bgcolor = AGNES_BGCOLOR;
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
            console.log("[AgnesFlashSuite] Agnes 节点蓝色配色扩展已注册（" + AGNES_COLOR + " / " + AGNES_BGCOLOR + "）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 配色扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
