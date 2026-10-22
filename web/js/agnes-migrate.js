/**
 * Agnes Flash Suite —— 批量节点旧实例 widget 值一次性迁移（输入结构「N 槽→单输入」升级）
 *
 * 背景：Agnes 套件的批量节点输入结构由「N 路手接槽 + 配置项」升级为
 * 「1 路 JSON 合并输入 + 配置项」。旧工作流里已保存的节点 widgets_values
 * 仍按旧结构序列化，载入后前端按索引映射到新 widget：第 1 槽（新 STRING
 * 输入）取到旧第 2 槽的空串 → 队列校验报 "Value not in list" / 值错乱。
 *
 * 迁移表（widgets_values 长度=旧结构指纹 → 重映射到新结构）：
 *   AgnesScenePromptBatch       分镜提示词批量    61 → 12 （旧 [50..60] 配置尾部 → 新 [1..11]）
 *   AgnesAssetPromptBatch      资产提示词批量    27 → 8  （旧 [20..26] 7 配置 → 新 [1..7]）
 *   AgnesTurnaroundPromptBatch 三视图提示词批量  26 → 7  （旧 [20..25] 6 配置 → 新 [1..6]）
 *   AgnesTurnaroundBatch       三视图批量生成    26 → 7  （旧 [20..25] 6 配置 → 新 [1..6]）
 * 规则：新 [0]=""（新合并输入槽留空，输入链接优先），新 [1..K]=旧配置项尾部原样保留。
 * 幂等：迁移后长度为新长度，重复执行不再命中。
 * 仍报错的兜底：删节点重加（右键 Agnes Novel → 对应节点）后重连。
 */
(function () {
    "use strict";

    var MIGRATIONS = [
        { cls: "AgnesScenePromptBatch", oldLen: 61, newLen: 12, tailStart: 50 },
        { cls: "AgnesAssetPromptBatch", oldLen: 27, newLen: 8, tailStart: 20 },
        { cls: "AgnesTurnaroundPromptBatch", oldLen: 26, newLen: 7, tailStart: 20 },
        { cls: "AgnesTurnaroundBatch", oldLen: 26, newLen: 7, tailStart: 20 },
    ];

    function migrate(node) {
        if (!node || !node.comfyClass) return;
        for (var m = 0; m < MIGRATIONS.length; m++) {
            var conf = MIGRATIONS[m];
            if (node.comfyClass !== conf.cls) continue;
            var wv = node.widgets_values;
            if (!Array.isArray(wv) || wv.length !== conf.oldLen) return; // 非旧结构，不动
            var migrated = [""];
            for (var i = conf.tailStart; i < conf.oldLen; i++) migrated.push(wv[i]);
            node.widgets_values = migrated;
            // 同步已创建的 widget 对象（Vue/旧版前端序列化可能读 widget.value）
            if (node.widgets) {
                for (var w = 0; w < node.widgets.length; w++) {
                    if (w < migrated.length && node.widgets[w]) node.widgets[w].value = migrated[w];
                }
            }
            if (node.setDirtyWidgets) node.setDirtyWidgets(true, true);
            if (node.setSize) node.setSize();
            return;
        }
    }

    function migrateAll() {
        var g = null;
        try { g = api && api.graph; } catch (e) { g = null; }
        if (!g || !g.nodes) return;
        for (var i = 0; i < g.nodes.length; i++) migrate(g.nodes[i]);
    }

    var extension = {
        name: "AgnesFlashSuite.BatchNodeMigrate",

        // 节点创建（含 graph.configure 载入旧图）时立即迁移
        nodeCreated: function (node) { migrate(node); },

        // 启动兜底（已存在的图）
        init: function (app) {
            try {
                var g = app && app.graph;
                if (!g || !g.nodes) return;
                for (var i = 0; i < g.nodes.length; i++) migrate(g.nodes[i]);
                if (g.setDirty) g.setDirty(true, true);
            } catch (e) { /* 忽略：迁移失败不影响节点功能 */ }
        },
    };

    var api = null;
    if (typeof window !== "undefined" && window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app) {
        api = window.comfyAPI.app.app; // 新 Vue 前端
    } else if (typeof app !== "undefined") {
        api = app;                     // 旧 JS 前端（legacy shim 兼容）
    }

    if (api && api.registerExtension) {
        try {
            api.registerExtension(extension);
            // 排队执行前再兜一层：graphToPrompt 序列化前 widget 值必须已校正
            if (typeof api.queuePrompt === "function") {
                var origQueuePrompt = api.queuePrompt;
                api.queuePrompt = function () {
                    migrateAll();
                    return origQueuePrompt.apply(this, arguments);
                };
            }
            console.log("[AgnesFlashSuite] Agnes 批量节点旧实例 widget 值迁移扩展已注册（分镜批量 61→12；资产批量 27→8；三视图提示词批量/三视图批量 26→7）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 迁移扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
