/**
 * Agnes Flash Suite —— 分镜提示词批量生成节点旧实例 widget 值一次性迁移
 *
 * 背景：AgnesScenePromptBatch 输入结构由 61 输入（50 槽 scene_1..50 + 11 配置项）
 * 重构为 12 输入（all_scenes 单输入 + 11 配置项）。旧工作流里已保存的节点
 * widgets_values 仍按 61 槽序列化，载入后前端按索引映射到新 12 个 widget：
 * 第 1 槽（style）取到旧 scene_2 的空串 → 队列校验报
 * "Value not in list: style: '' not in ['cinematic', ...]"，同类的还有
 * model / reasoning_effort 等下拉槽。
 *
 * 修复：节点创建（含工作流载入）与排队执行前，若 widgets_values 恰为 61 槽
 * （旧结构特征），重映射为 12 槽：
 *   新 [0]   all_scenes      = ""（输入链接优先，widget 值仅兜底）
 *   新 [1..11] style/资产×5/base_url/api_key/model/reasoning_effort/max_concurrency
 *              = 旧 [50..60]（用户原有 widget 设置完整保留）
 * 幂等：迁移后长度为 12，重复执行不再命中。
 * 仍报错的兜底：删节点重加（右键 Agnes Novel → Agnes 分镜提示词批量生成）后重连。
 */
(function () {
    "use strict";

    var NEW_LEN = 12;
    var OLD_LEN = 61;
    var OLD_TAIL_START = 50; // 旧槽 50..60 = style..max_concurrency

    function migrate(node) {
        if (!node || node.comfyClass !== "AgnesScenePromptBatch") return;
        var wv = node.widgets_values;
        if (!Array.isArray(wv) || wv.length !== OLD_LEN) return;
        var migrated = [""];
        for (var i = 0; i < OLD_LEN - OLD_TAIL_START; i++) migrated.push(wv[OLD_TAIL_START + i]);
        node.widgets_values = migrated;
        // 同步已创建的 widget 对象（Vue/旧版前端序列化可能读 widget.value）
        if (node.widgets) {
            for (var w = 0; w < node.widgets.length; w++) {
                if (w < NEW_LEN && node.widgets[w]) node.widgets[w].value = migrated[w];
            }
        }
        if (node.setDirtyWidgets) node.setDirtyWidgets(true, true);
        if (node.setSize) node.setSize();
    }

    function migrateAll() {
        var g = null;
        try { g = api && api.graph; } catch (e) { g = null; }
        if (!g || !g.nodes) return;
        for (var i = 0; i < g.nodes.length; i++) migrate(g.nodes[i]);
    }

    var extension = {
        name: "AgnesFlashSuite.ScenePromptBatchMigrate",

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
            console.log("[AgnesFlashSuite] Agnes 分镜提示词批量 旧实例 widget 值迁移扩展已注册（61→12 槽）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 迁移扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
