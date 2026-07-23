# Markdown fence 验证

Markdown 结构计数前必须先调用 `@markdown_fences.py`，不得再用 fence 行数奇偶或跨行正则判断代码块是否闭合。

## 权威接口

```python
from markdown_fences import scan_fenced_blocks, strip_fenced_blocks

blocks = scan_fenced_blocks(markdown)  # 未闭合或错误闭合时抛 ValueError
no_code = strip_fenced_blocks(markdown)
```

- `scan_fenced_blocks()` 按行维护 opener/closer 状态；
- 支持反引号和波浪号 fence；
- closer 必须使用相同字符，且长度不短于 opener；
- 支持 4+ 反引号外层包住较短的 inner fence；
- 支持 blockquote 和列表项中的 fence；
- 列表项中的 closer 必须仍位于该列表项的内容缩进范围内，顶格 fence 不得关闭列表项中的代码块；
- 非法 closer 会报告具体原因，例如字符不一致、长度不足、容器缩进错误或尾随文本；
- `strip_fenced_blocks()` 保留原行数和换行符，供标题、列表、blockquote 等结构扫描使用。

## 阻断规则

以下任一情况都必须阻断交付：

- opener 到文件末尾仍未闭合；
- 使用不同字符尝试闭合，例如 backtick opener 配 tilde closer；
- closer 比 opener 短；
- closer 后存在非空尾随文本；
- blockquote 容器深度不匹配；
- 列表项 fence 被容器外的顶格 fence 尝试关闭；
- 结构计数没有先调用 `strip_fenced_blocks()`。

## 为什么不能只数奇偶

下面的输入中，backtick fence 行和 tilde fence 行分别都是偶数，但最后一个 tilde opener 没有闭合：

````markdown
```python
code
~~~
```
~~~
````

因此 `n % 2 == 0` 不是“配对完整”的证明。简单的 `re.sub(r'```.*?```', ...)` 也无法正确处理更长的 outer fence、tilde fence、blockquote 或列表嵌套。

## 列表容器示例

以下 closer 合法，因为它保持在列表内容缩进内：

````markdown
- ```python
  print("inside")
  ```
````

以下顶格 fence 已离开列表项，不能关闭上面的代码块，必须阻断并报告容器缩进错误：

````markdown
- ```python
  print("inside")
```
````

## Outer fence

生成包含 inner fence 的输出时，outer fence 的长度必须大于内容中最长的同字符 fence。例如内容中最长 backtick run 为 4，则 outer 至少使用 5 个 backtick。生成后仍必须执行 `scan_fenced_blocks()`，不能只依赖生成前估算。
