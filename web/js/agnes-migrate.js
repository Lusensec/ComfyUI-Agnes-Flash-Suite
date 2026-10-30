/**
 * Agnes Flash Suite —— 旧实例 widget 值一次性迁移（结构升级后自动重映射）
 *
 * 背景：Agnes 套件的节点输入结构多次升级（批量节点「N 槽→单输入」、
 * 视频节点移除 1K/2K 档位、视频节点 帧数/帧率 改 秒数 直控 + 加 720P 分辨率项），
 * 旧工作流里已保存的节点 widgets_values 仍按旧结构序列化，载入后前端按索引
 * 映射到新 widget：取值错位 → 队列校验报 "Value not in list" / 值错乱。
 *
 * 迁移表（widgets_values 长度=旧结构指纹 → 重映射到新结构）：
 *   AgnesScenePromptBatch       分镜提示词批量    61 → 12 （旧 [50..60] 配置尾部 → 新 [1..11]）
 *   AgnesAssetPromptBatch      资产提示词批量    27 → 8  （旧 [20..26] 7 配置 → 新 [1..7]）
 *   AgnesTurnaroundPromptBatch 三视图提示词批量  26 → 7  （旧 [20..25] 6 配置 → 新 [1..6]）
 *   AgnesTurnaroundBatch       三视图批量生成    26 → 7  （旧 [20..25] 6 配置 → 新 [1..6]）
 * 规则：新 [0]=""（新合并输入槽留空，输入链接优先），新 [1..K]=旧配置项尾部原样保留。
 * 视频任务批量收取 置顶新增 all_task_url_keys 合并输入：23 → 24（旧 [0..22] 整体
 * 下移一格为 新 [1..23]，新 [0]=合并输入留空；新结构 24 项实例不命中 23 指纹，幂等）。
 *
 * 视频节点三段演进（按数组顺序逐段应用，一个节点可连续命中多段）：
 * ① quality（1K/2K）档位移除 —— 中位截断，按 dropIdx 丢格重排：
 *    AgnesNovelTextToVideo  10 → 9（丢档位，旧索引 4）
 *    AgnesNovelImageToVideo 10 → 9（丢档位，旧索引 4）
 *    AgnesVideoReference    13 → 12（丢档位，旧索引 6）
 * ② 帧数/帧率 改 秒数直控 + 模型单项化 + 加 720P 分辨率项 —— 按 map 重排：
 *    新文生视频/关键帧 9 项：[提示词,base_url,key,模型,720P,宽高比,秒数,种子,超时]
 *    新参考视频 12 项：同上前 9 项 + [音频1,音频2,音频3]
 *    秒数由旧 帧数/帧率 推导（round，4-12 钳位），模型固定 Agnes Video 2.5-flash
 * 指纹：长度匹配 + 位置值特征（旧 [4]=含":"的宽高比串 / 旧参考视频 [4]=数值帧数；
 * 新结构 [4]="720P" 无冒号 → 不再命中，幂等）。
 * flex：折叠态实例 widgets_values 末尾可能多 1 个隐藏值（长度 oldLen+1），
 * 自动剥离并原样保留在迁移结果末尾。
 * ① dropIdx 条目限定旧档位值指纹（[4]/[6] = "1K"/"2K"）：新增「重试次数」尾参后，
 * 新结构文生/关键帧 10 项、参考视频 13 项与旧档位实例同长度，靠该指纹避免误删；
 * 「重试次数」为纯尾部新增 widget，旧实例载入时自动补默认值 5，无需迁移条目。
 * 图像模型单项化（2.1/2.0 下线）：5 个图像节点同长度重映射，仅把 model 槽位旧值
 * （agnes-image-2.1/2.0-flash）换成 agnes-image-2.5-flash，指纹限定旧模型值，幂等。
 * 仍报错的兜底：删节点重加（右键 Agnes Novel → 对应节点）后重连。
 */
(function () {
    "use strict";

    var NEW_MODEL = "agnes-video-2.5-flash";
    var NEW_RES = "720P";
    var NEW_IMAGE_MODEL = "agnes-image-2.5-flash";

    // 图像模型单项化（2.1/2.0 下线）：同长度重映射，仅替换 model 槽位值为 2.5-flash
    function isOldImageModel(v) { return v === "agnes-image-2.1-flash" || v === "agnes-image-2.0-flash"; }
    function remapImageModel(wv, idx) { var c = wv.slice(); c[idx] = NEW_IMAGE_MODEL; return c; }

    // 由旧 帧数/帧率 推导 秒数（4-12 钳位；缺省 5）
    function deriveSecs(nf, fr) {
        var s = 5;
        if (nf && fr) s = Math.round(nf / fr);
        if (s < 4) s = 4;
        if (s > 12) s = 12;
        return s;
    }

    // 旧 9 项文生/关键帧 [提示词,base_url,key,模型,宽高比,帧数,帧率,种子,超时]
    // → 新 9 项 [提示词,base_url,key,模型,720P,宽高比,秒数,种子,超时]
    function mapT2vI2v(wv) {
        return [
            wv[0], wv[1], wv[2], NEW_MODEL, NEW_RES,
            wv[4], deriveSecs(wv[5], wv[6]), wv[7], wv[8]
        ];
    }

    // 旧 12 项参考视频 [提示词,base_url,key,模型,帧数,帧率,宽高比,种子,超时,音频x3]
    // → 新 12 项 [提示词,base_url,key,模型,720P,宽高比,秒数,种子,超时,音频x3]
    function mapVref(wv) {
        return [
            wv[0], wv[1], wv[2], NEW_MODEL, NEW_RES,
            wv[6], deriveSecs(wv[4], wv[5]), wv[7], wv[8],
            wv[9], wv[10], wv[11]
        ];
    }

    var MIGRATIONS = [
        // —— 批量节点：N 槽 → 单输入（尾部配置项重排）——
        { cls: "AgnesScenePromptBatch", oldLen: 61, newLen: 12, tailStart: 50 },
        { cls: "AgnesAssetPromptBatch", oldLen: 27, newLen: 8, tailStart: 20 },
        { cls: "AgnesTurnaroundPromptBatch", oldLen: 26, newLen: 7, tailStart: 20 },
        { cls: "AgnesTurnaroundBatch", oldLen: 26, newLen: 7, tailStart: 20 },
        // —— 批量收取：置顶新增 all_task_url_keys 合并输入（头部纯新增 widget；
        //    旧 23 项实例自动前补 ""，旧 [0..22] 整体下移一格；新 24 项实例不命中，幂等）——
        {
            cls: "AgnesVideoTaskCollectBatch", oldLen: 23, newLen: 24,
            map: function (wv) {
                var c = [""];
                for (var i = 0; i < wv.length; i++) c.push(wv[i]);
                return c;
            }
        },
        // —— 视频 ①：1K/2K 档位移除（中位丢格；指纹限定旧档位值，避免误伤
        //    新结构同长度实例：文生/关键帧 10 项[idx4=720P]、参考视频 13 项[idx6=秒数]）——
        {
            cls: "AgnesNovelTextToVideo", oldLen: 10, newLen: 9, dropIdx: 4, flex: true,
            fingerprint: function (wv) { return wv[4] === "1K" || wv[4] === "2K"; }
        },
        {
            cls: "AgnesNovelImageToVideo", oldLen: 10, newLen: 9, dropIdx: 4, flex: true,
            fingerprint: function (wv) { return wv[4] === "1K" || wv[4] === "2K"; }
        },
        {
            cls: "AgnesVideoReference", oldLen: 13, newLen: 12, dropIdx: 6, flex: true,
            fingerprint: function (wv) { return wv[6] === "1K" || wv[6] === "2K"; }
        },
        // —— 视频 ②：帧数/帧率 → 秒数直控 + 模型单项 + 720P 分辨率项（值指纹重排）——
        {
            cls: "AgnesNovelTextToVideo", oldLen: 9, newLen: 9, flex: true,
            fingerprint: function (wv) {
                return typeof wv[4] === "string" && wv[4].indexOf(":") !== -1;
            },
            map: mapT2vI2v
        },
        {
            cls: "AgnesNovelImageToVideo", oldLen: 9, newLen: 9, flex: true,
            fingerprint: function (wv) {
                return typeof wv[4] === "string" && wv[4].indexOf(":") !== -1;
            },
            map: mapT2vI2v
        },
        {
            cls: "AgnesVideoReference", oldLen: 12, newLen: 12, flex: true,
            fingerprint: function (wv) {
                return typeof wv[4] === "number";
            },
            map: mapVref
        },
        // —— 图像：模型单项化（2.1/2.0 下线，统一 2.5-flash）：同长度重映射，
        //    仅替换 model 槽位旧值，其余原样；指纹限定旧模型值，2.5 实例不命中（幂等）——
        {
            cls: "AgnesImageGen", oldLen: 9, newLen: 9,
            fingerprint: function (wv) { return isOldImageModel(wv[3]); },
            map: function (wv) { return remapImageModel(wv, 3); }
        },
        {
            cls: "AgnesNovelImageToImage", oldLen: 8, newLen: 8,
            fingerprint: function (wv) { return isOldImageModel(wv[3]); },
            map: function (wv) { return remapImageModel(wv, 3); }
        },
        {
            cls: "AgnesSubjectTurnaround", oldLen: 7, newLen: 7,
            fingerprint: function (wv) { return isOldImageModel(wv[3]); },
            map: function (wv) { return remapImageModel(wv, 3); }
        },
        {
            cls: "AgnesSceneImageBatch", oldLen: 7, newLen: 7,
            fingerprint: function (wv) { return isOldImageModel(wv[5]); },
            map: function (wv) { return remapImageModel(wv, 5); }
        },
        {
            cls: "AgnesTurnaroundBatch", oldLen: 7, newLen: 7,
            fingerprint: function (wv) { return isOldImageModel(wv[3]); },
            map: function (wv) { return remapImageModel(wv, 3); }
        }
    ];

    function applyOne(node, conf, body, extra) {
        var migrated;
        if (typeof conf.map === "function") {
            migrated = conf.map(body);
        } else if (conf.dropIdx !== undefined) {
            // 中位删格（视频 1K/2K 档位移除）：丢 dropIdx，其余原样前移
            migrated = body.filter(function (_, i) { return i !== conf.dropIdx; });
        } else {
            migrated = [""];
            for (var i = conf.tailStart; i < conf.oldLen; i++) migrated.push(body[i]);
        }
        if (extra !== null) migrated.push(extra);
        node.widgets_values = migrated;
        // 同步已创建的 widget 对象（Vue/旧版前端序列化可能读 widget.value）
        if (node.widgets) {
            for (var w = 0; w < node.widgets.length; w++) {
                if (w < migrated.length && node.widgets[w]) node.widgets[w].value = migrated[w];
            }
        }
        return true;
    }

    function migrate(node) {
        if (!node || !node.comfyClass) return;
        var applied = false;
        var used = {}; // 每条迁移每节点最多应用一次（防 flex 折叠值尾部长度=oldLen 导致同段误重命中）
        // 一个节点可能连续命中多段（① 10→9 后 ② 9→9），重扫直到无命中（上限 4 段防死循环）
        for (var pass = 0; pass < 4; pass++) {
            var hit = false;
            for (var m = 0; m < MIGRATIONS.length; m++) {
                var conf = MIGRATIONS[m];
                if (node.comfyClass !== conf.cls || used[m]) continue;
                var wv = node.widgets_values;
                if (!Array.isArray(wv)) return;
                var extra = null;
                var body = wv;
                if (conf.flex && wv.length === conf.oldLen + 1) {
                    extra = wv[wv.length - 1]; // 折叠态末尾隐藏值：剥离并保留
                    body = wv.slice(0, conf.oldLen);
                }
                if (body.length !== conf.oldLen) continue;
                if (conf.fingerprint && !conf.fingerprint(body)) continue;
                used[m] = true;
                if (applyOne(node, conf, body, extra)) {
                    hit = true;
                    break; // 重扫（后面可能还有同类的下一段）
                }
            }
            if (!hit) break;
            applied = true;
        }
        if (applied) {
            if (node.setDirtyWidgets) node.setDirtyWidgets(true, true);
            if (node.setSize) node.setSize();
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
            console.log("[AgnesFlashSuite] Agnes 旧实例 widget 值迁移扩展已注册（批量节点 61→12 / 27→8 / 26→7；批量收取置顶合并输入 23→24；视频节点三段：丢 1K/2K 档位 10→9 / 13→12 → 帧数帧率改秒数+720P 重排 9→9 / 12→12；图像节点模型单项化：旧 2.1/2.0 值重映射到 2.5-flash）");
        } catch (e) {
            console.warn("[AgnesFlashSuite] 迁移扩展注册失败（不影响节点功能）:", e);
        }
    }
})();
