/**
 * Agnes 字符串展示（AgnesStringDisplay）—— 在节点身体内显示连入文本
 *
 * 机制仿 ComfyUI-Custom-Scripts 的 Show Text（pysssss.ShowText）：
 *   ① Python 端执行返回 {"ui": {"text": ...}, "result": (text,)}，
 *      核心执行引擎随 "executed" 推送给前端 → 调用本节点实例的 onExecuted(ui)
 *   ② 本扩展钩 onExecuted → 在节点身体内动态创建只读多行控件显示文本，
 *      并自动撑大节点
 *   ③ Python 端执行时把 widgets_values=[text] 写回工作流内存（extra_pnginfo），
 *      保存/重载工作流后由本扩展的 onConfigure 钩子从存档恢复上次显示
 *
 * 兼容：Vue 前端（comfyui-frontend-package）的 legacy shim（scripts/app.js、
 *       scripts/widgets.js）与旧 JS 前端均可加载；beforeRegisterNodeDef 双签名自适应。
 * 退化：环境缺 legacy shim 时本文件加载失败，节点退化为「仅控制台日志 + 透传」，
 *       不影响 Python 端功能。
 */
import { app } from "../../../scripts/app.js";
import { ComfyWidgets } from "../../../scripts/widgets.js";

const NODE_NAME = "AgnesStringDisplay";
const VALUES = Symbol();

// 在节点身体内渲染要显示的文本（可传字符串数组，每条一个只读控件）
function populate(node, text) {
    // 1. 移除此前动态创建的展示控件（保留原有/转换控件）
    if (node.widgets?.length) {
        const isConvertedWidget = +!!node.inputs?.[0]?.widget;
        for (let i = node.widgets.length - 1; i >= isConvertedWidget; i--) {
            if (node.widgets[i]?.type === "agnes-string-display") {
                node.widgets[i].onRemove?.();
                node.widgets.splice(i, 1);
            }
        }
    }

    // 2. 为每条字符串创建一个只读多行控件
    const v = [...text];
    if (!v[0]) v.shift();
    for (let list of v) {
        if (!(list instanceof Array)) list = [list];
        for (const s of list) {
            if (typeof s !== "string" || !s) continue;
            const w = ComfyWidgets["STRING"](node, "text_" + node.widgets?.length, ["STRING", { multiline: true }], app).widget;
            w.type = "agnes-string-display";
            w.inputEl.readOnly = true;
            w.inputEl.style.opacity = 0.6;
            w.value = s;
        }
    }

    // 3. 自动调整节点尺寸并重绘
    requestAnimationFrame(() => {
        const sz = node.computeSize();
        if (sz[0] < node.size[0]) sz[0] = node.size[0];
        if (sz[1] < node.size[1]) sz[1] = node.size[1];
        node.onResize?.(sz);
        app.graph?.setDirtyCanvas?.(true, false);
    });
}

app.registerExtension({
    name: "AgnesFlashSuite.StringDisplay",

    async beforeRegisterNodeDef(arg1, arg2) {
        // Vue 前端：beforeRegisterNodeDef(nodeClass, nodeDef, app)
        // 旧 JS 前端：beforeRegisterNodeDef(nodeDef, nodeClass)
        const nodeType = typeof arg1 === "function" ? arg1 : arg2;
        const nodeData = arg1 !== undefined && typeof arg1 === "object" ? arg1 : arg2;
        if (!nodeType || !nodeData || nodeData.name !== NODE_NAME) return;

        // ② 执行完成后收到 ui 回写 → 更新身体显示
        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            if (message && "text" in message) {
                populate(this, [message.text]);
            }
        };

        // ③ 加载工作流：保存原始 widgets_values（新前端在 configure 阶段会处理初始控件）
        const configure = nodeType.prototype.configure;
        nodeType.prototype.configure = function () {
            this[VALUES] = arguments[0]?.widgets_values;
            return configure?.apply(this, arguments);
        };

        // 加载完成后从存档恢复上次显示
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            onConfigure?.apply(this, arguments);
            const widgets_values = this[VALUES];
            if (widgets_values?.length) {
                requestAnimationFrame(() => {
                    // 展示控件值在 widgets_values 末尾；若存在转换控件则跳过首槽
                    populate(this, widgets_values.slice(+(widgets_values.length > 1 && this.inputs?.[0]?.widget)));
                });
            }
        };
    },
});

console.log("[AgnesFlashSuite] 字符串展示上屏扩展已注册（AgnesStringDisplay）");
