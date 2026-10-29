/**
 * Agnes Flash Suite —— 「Agnes 视频任务并发结果」实时矩阵渲染（ShowText 化）
 *
 * 背景：并发结果 节点是计算型展示终端——result 输出只在节点被"执行"后生成。
 * 本扩展给它加一个**只读 DOM 多行文本框「实时结果（自动刷新）」**（节点最下方），
 * 内容 = 用与后端 generate() 完全相同的格式规则，在前端实时渲染的逐条目矩阵：
 *   - 数据来源（按优先级）：
 *     ① 上游提交节点执行完成后本扩展捕获的输出值（node.onExecuted 钩子）
 *     ② 平台缓存的 output.value（若该前端版本写入）
 *     ③ 平台 nodeOutputs 映射（status 消息携带 output 时写入）
 *     ④ 本节点自身三个输入框的值（手动粘贴 JSON / 平台连线同步后的 widget 值）
 *   - 刷新时机：每 800ms 全量 diff 检查 + 上游执行完成立即刷新；值不变则零 DOM 写入
 * 后端 generate() / result 输出零改动——想要 LLM 台账仍走"执行"语义，两条路并存。
 *
 * 兼容：新 Vue 前端（comfyui-frontend：node.addDOMWidget，同平台 addMultilineWidget 造法）
 *       与旧 JS 前端（node.addWidget 字符串 widget 兜底，单行显示）。
 * 失败安全：任何异常只打 console.warn，不影响节点功能。
 */
(function () {
    "use strict";

    var RESULT_NODE = "AgnesVideoTaskPoolStatus";
    var SOURCE_NODES = {
        "AgnesVideoTaskSubmitPool": true,   // 并发提交（池线主源）
        "AgnesVideoTaskSubmit": true        // 单提交（混线兜底，输出名同族）
    };
    var LIVE_WIDGET_NAME = "实时结果（自动刷新）";
    var INPUT_NAMES = ["task_url_key", "pool_report", "status"];
    var TICK_MS = 800;

    // ── 与后端 api._mask_key 逐条对齐（len>12 前8+****+后4；6<len≤12 前3+****+后3；其余 ****）──
    function maskKey(k) {
        k = String(k == null ? "" : k);
        if (!k) return "(empty)";
        if (k.length > 12) return k.slice(0, 8) + "****" + k.slice(-4);
        if (k.length > 6) return k.slice(0, 3) + "****" + k.slice(-3);
        return "****";
    }

    // ── 与后端 generate() 完全相同的矩阵格式（【状态】/【胜出】/【逐条目矩阵】）──
    function buildMatrix(status, poolReport, tuku) {
        status = String(status == null ? "" : status).trim();
        poolReport = String(poolReport == null ? "" : poolReport).trim();
        tuku = String(tuku == null ? "" : tuku).trim();

        var lines = ["【状态】" + (status || "（无状态：并发提交 节点未运行或未连线）")];

        // 【胜出】
        var tukuObj = null;
        if (tuku) {
            try { tukuObj = JSON.parse(tuku); } catch (e) { tukuObj = null; }
        }
        if (tukuObj && typeof tukuObj === "object" && !Array.isArray(tukuObj)) {
            var url = String(tukuObj.task_url || "").trim();
            var wkey = String(tukuObj.api_key || "").trim();
            if (url && url !== "0") {
                lines.push("【胜出】" + maskKey(wkey) + "（task_url_key 非 0 标记，可直连「Agnes 视频任务批量收取」的 task_i 槽，批量收取 节点零改动）");
            } else {
                lines.push("【胜出】无（task_url_key=0 标记：未生成任务，批量收取 见 0 跳过记 error；请 5-10 分钟后重跑 并发提交 节点）");
            }
        } else if (tuku) {
            lines.push("【胜出】task_url_key 解析失败: " + tuku.slice(0, 80));
        }

        // 【逐条目矩阵】
        var rep = [];
        if (poolReport && poolReport !== "[]" && poolReport !== "0") {
            try {
                var obj = JSON.parse(poolReport);
                if (Array.isArray(obj)) rep = obj.filter(function (e) { return e && typeof e === "object"; });
            } catch (e) { rep = []; }
        }
        if (rep.length) {
            lines.push("【逐条目矩阵】");
            for (var i = 0; i < rep.length; i++) {
                var e = rep[i];
                var base = e.base_url || "(全局)";
                lines.push(" #" + e.i + " " + base + " " + e.key + " → " + e.result + "（attempts=" + (e.attempts || 0) + "）");
            }
        } else {
            lines.push("【逐条目矩阵】（无报告：池为空 / 零请求短路 / 未连线）");
        }
        return lines.join("\n");
    }

    // ── 数据源：某输入名的当前值（多层兜底）──
    function widgetValue(node, name) {
        var ws = node.widgets || [];
        for (var i = 0; i < ws.length; i++) {
            if (ws[i] && ws[i].name === name) return ws[i].value == null ? "" : String(ws[i].value);
        }
        return "";
    }

    // 本 LiteGraph 版本里 input.link 是 **link ID（number）**，
    // 源节点 = graph.links[linkId].origin_id；旧版数组格式 [origin_id,...] 也兼容。
    function resolveLinkSource(node, app, inp) {
        if (!inp || inp.link == null) return null;
        var g = app && app.graph;
        if (!g) return null;
        if (Array.isArray(inp.link)) {
            return g.getNodeById(inp.link[0]);      // 旧版数组格式
        }
        var linkObj = g.links && g.links[inp.link];
        if (linkObj) return g.getNodeById(linkObj.origin_id);
        return null;
    }

    function inputValue(node, name, app) {
        var inps = node.inputs || [];
        for (var i = 0; i < inps.length; i++) {
            var inp = inps[i];
            if (!inp || inp.name !== name) continue;
            if (inp.link != null) {
                var src = resolveLinkSource(node, app, inp);
                if (src) {
                    // ① 本扩展在源节点 onExecuted 捕获的输出
                    if (src._agnesLiveOut && src._agnesLiveOut[name] != null && src._agnesLiveOut[name] !== "")
                        return String(src._agnesLiveOut[name]);
                    // ② 平台 output.value 缓存（若该前端写入）
                    var outs = src.outputs || [];
                    for (var j = 0; j < outs.length; j++) {
                        if (outs[j].name === name && outs[j].value != null && outs[j].value !== "")
                            return String(outs[j].value);
                    }
                    // ③ 平台 nodeOutputs 映射（status 消息携带 output 时）
                    if (app && app.nodeOutputs && app.nodeOutputs[src.id] && app.nodeOutputs[src.id][name] != null)
                        return String(app.nodeOutputs[src.id][name]);
                }
            }
            break;
        }
        // ④ 本节点自身输入框值（手动粘贴 / 平台连线同步后的 widget 值）
        return widgetValue(node, name);
    }

    // ── 实时结果 DOM 文本框（平台同款 customtext 造法）──
    function addLiveWidget(node) {
        if (node._agnesLiveEl) return;
        try {
            var el = document.createElement("textarea");
            el.className = "comfy-multiline-input";
            el.spellcheck = false;
            el.readOnly = true;
            el.value = "（暂无值：先运行「Agnes 视频任务并发提交」，或在上方输入框手动粘贴 JSON）";
            var w;
            if (typeof node.addDOMWidget === "function") {
                // 新 Vue 前端（与平台 useStringWidget.addMultilineWidget 同路）
                w = node.addDOMWidget(LIVE_WIDGET_NAME, "customtext", el, {
                    getValue: function () { return el.value; },
                    setValue: function (v) { el.value = String(v == null ? "" : v); }
                });
                w.inputEl = el;
            } else {
                // 旧 JS 前端兜底：普通字符串 widget（单行显示）
                w = node.addWidget("string", LIVE_WIDGET_NAME, el.value, function (v) {}, {});
            }
            try { w.serialize = false; } catch (e) { /* 旧版无此标记时忽略 */ }
            // 与平台 addMultilineWidget 同款：最小节点尺寸约束（参与自动布局）
            try {
                w.options = w.options || {};
                w.options.minNodeSize = [460, 260];
            } catch (e) { /* 忽略 */ }
            node._agnesLiveEl = el;
            node._agnesLiveWidget = w;
            node._agnesLiveLast = null;
            // 给文本框留出空间：只在节点已有确定尺寸时增高（Vue 层管理尺寸的节点
            // 尺寸为 null 时交给平台自动布局，不强写，避免与响应式布局打架）
            try {
                var s = node.size;
                if (s && s[0] && s[1]) node.setSize(Math.max(s[0], 460), s[1] + 230);
            } catch (e) { /* 忽略 */ }
            refresh(node, getCurrentApi());
        } catch (e) {
            console.warn("[AgnesFlashSuite] 实时结果框创建失败（不影响节点功能）:", e);
        }
    }

    // ── 刷新一个 并发结果 节点的实时矩阵 ──
    function refresh(node, app) {
        if (!node._agnesLiveEl) return;
        var text = buildMatrix(
            safeInputValue(node, "status", app),
            safeInputValue(node, "pool_report", app),
            safeInputValue(node, "task_url_key", app)
        );
        if (text === node._agnesLiveLast) return;
        node._agnesLiveLast = text;
        var el = node._agnesLiveEl;
        if (el.value !== text) el.value = text;
        var w = node._agnesLiveWidget;
        if (w && w.setValue) { try { w.setValue(text); } catch (e) { /* 忽略 */ } }
    }

    // app 未就绪（nodeCreated 早于前端 app 初始化）时退化为只看本节点 widget 值
    function safeInputValue(node, name, app) {
        try {
            return inputValue(node, name, app);
        } catch (e) {
            return widgetValue(node, name);
        }
    }

    function refreshAll(app) {
        var g = app && app.graph;
        if (!g || !g.nodes) return;
        for (var i = 0; i < g.nodes.length; i++) {
            var n = g.nodes[i];
            if (n && n.comfyClass === RESULT_NODE) refresh(n, app);
        }
    }

    // ── 节点接入：结果节点加实时框；提交节点挂执行完成捕获 ──
    // 注意：app 一律在"刷新时刻"实时获取（getCurrentApi），不在 wrap 时捕获——
    // 节点创建可能早于前端 app 就绪，捕获 null 会导致 onExecuted 刷新静默失效。
    function wrapNode(node) {
        if (!node || !node.comfyClass) return;
        if (node.comfyClass === RESULT_NODE) {
            addLiveWidget(node);
        } else if (SOURCE_NODES[node.comfyClass] && !node._agnesLiveWrapped) {
            node._agnesLiveWrapped = true;
            // 平台在"执行完成"status 消息里调用 node.onExecuted(output)（output=按输出名索引的值 dict）
            node.onExecuted = function (output) {
                node._agnesLiveOut = output || {};
                refreshAll(getCurrentApi());   // 立即刷新所有 并发结果 实时框
            };
        }
    }

    var extension = {
        name: "AgnesFlashSuite.PoolLive",

        nodeCreated: function (node) {
            wrapNode(node);
        },

        init: function (app) {
            try {
                var g = app && app.graph;
                if (g && g.nodes) {
                    for (var i = 0; i < g.nodes.length; i++) wrapNode(g.nodes[i]);
                }
                refreshAll(app || getCurrentApi());
            } catch (e) { /* 忽略 */ }
            if (!extension._timer) {
                extension._timer = setInterval(function () {
                    var api = getCurrentApi();
                    if (api) refreshAll(api);
                }, TICK_MS);
            }
        }
    };

    function getCurrentApi() {
        if (typeof window === "undefined") return null;
        if (window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app) return window.comfyAPI.app.app;
        if (typeof app !== "undefined" && app) return app;
        return null;
    }

    var api = getCurrentApi();
    if (api && api.registerExtension) {
        try {
            api.registerExtension(extension);
            console.log("[AgnesFlashSuite] 并发结果 实时矩阵扩展已注册（「实时结果（自动刷新）」文本框：800ms diff 刷新 + 上游执行完成即时刷新；后端 generate/result 不变）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 实时矩阵扩展注册失败（不影响节点功能）:", e);
        }
    } else {
        console.warn("[AgnesFlashSuite] 未找到前端 app 实例，实时矩阵扩展未注册（并发结果 仍可正常执行使用）");
    }
})();
