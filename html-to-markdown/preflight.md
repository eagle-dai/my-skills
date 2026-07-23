# SingleFile 预检与精简快照

`preflight.py` 是 HTML 转换前的确定性入口。它的目标不是完成 Markdown 转换，而是避免主 agent 和 sub agent 反复读取完整 SingleFile 包装层。

## 使用

```bash
python html-to-markdown/preflight.py input.html --output work/preflight
```

输出：

```text
work/preflight/
├── content.html
├── manifest.json
├── formulas.json
└── assets.json
```

- `content.html`：唯一正文容器的精简 HTML；删除页面脚本、页面级样式和模板节点，但保留富文本与公式节点的 class、inline style 和 DOM 结构。
- `manifest.json`：schema version、正文 selector、输入/精简/可见文本体积、结构计数、风险信号和建议模式。
- `formulas.json`：公式 source ID、block/inline、来源能力、规范化 DOM hash 和可直接读取的原始 LaTeX。
- `assets.json`：图片、iframe 和 video 的 source 类型与长度；不把 data URI 二进制展开到 agent 上下文。

## Body 选择

按以下优先级寻找正文：

1. `[data-slate-editor]`
2. `article`
3. `main`
4. `[role="main"]`

第一个存在有效正文的优先级必须只有一个候选。多个 substantial 候选或没有语义正文时 fail closed，转入 strict 检查；不得通过“取最长文本”静默忽略另一篇正文。

## 模式建议

以下信号会推荐 `strict`：

- Notebook/cell 标记；
- Monaco、CodeMirror 或其他虚拟化编辑器；
- 空 `src` 或 lazy-load 资源占位。

普通静态文章推荐 `fast`。KaTeX HTML-only 公式本身不强制 strict；后续公式批处理器负责去重、解析和失败升级。

## Formula hash

公式 hash 对以下表面差异稳定：

- HTML attribute 顺序；
- class 顺序；
- 无语义文本空白；
- inline style declaration 顺序。

class 和 inline style 仍参与 hash，因为 KaTeX 视觉 DOM 可能依赖这些结构。hash 只用于同一次转换与缓存键，不表示两个公式数学语义必然等价。

## 阻断条件

- 正文 selector 不唯一；
- 正文文本不足；
- 正文无法序列化；
- 输入无法按 UTF-8 读取。

预检失败时不得退回“让 agent 猜正文”；调用方应进入现有 strict Playwright 流程。
