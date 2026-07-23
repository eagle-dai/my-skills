# 图片保留与删除判定

图片处理的权威可执行合同是 `@image_disposition.py`。不得仅凭“看起来像二维码”就删除图片。

## QR code 默认规则

| 场景 | 决策 |
|---|---|
| 正文步骤、产品说明、下载入口、联系方式、报名、认证或支付流程中的二维码 | `keep` |
| 与正文块、题注、相邻说明或关键链接存在明确内容关系 | `keep` |
| 分享栏、关注公众号浮层、登录弹窗等 UI 容器中的二维码，且与正文无关系 | `remove_as_ui` |
| 无法确认是正文还是 UI | `manual_review`，保留原图并标记复核 |

能够可靠解析二维码目标 URL 时，应在保留图片的同时输出可点击链接；解析失败不构成删除理由。

## 判定顺序

1. 为每张源图片建立稳定 `source_id`；
2. 记录是否为二维码、是否在正文内、是否有相邻内容关系、是否位于分享/关注 UI；
3. 调用 `decide_image()`；
4. 生成 image ledger；
5. 交付前调用 `assert_valid_image_ledger()`。

## Ledger

```text
source_id | decision | emitted_count | reason | decoded_url
```

约束：

- `keep`：原图必须输出一次；
- `manual_review`：原图仍必须输出一次，并写明不确定原因；
- `remove_as_ui`：输出次数为 0，且必须记录明确的 UI 证据；
- ledger 的 `source_id` 集合必须与源图片集合完全一致；
- 不允许“无法判断”直接转成删除。

## 示例

```python
from image_disposition import ImageContext, decide_image

context = ImageContext(
    source_id="img-12",
    is_qr_code=True,
    in_body=True,
    has_content_relation=True,
)
assert decide_image(context) == "keep"
```
