# ==================== AI修改 开始 ====================
# 这些测试只覆盖图片 URL 的纯逻辑，不连接 MinIO、MongoDB、Milvus 或大模型。
# 这样可以先验证“图片地址是否正确”这一条最关键的数据链路。
# ==================== AI修改 结束 ====================
from atguigu.tool.image_url_tool import (
    build_minio_image_url,
    collect_image_references_from_chunks,
    extract_image_references,
    normalize_image_urls,
    resolve_image_reference,
)


# ==================== AI修改 开始 ====================
# 验证 endpoint 已经带协议时不会重复拼接 http://，并且空格会被 URL 编码。
# ==================== AI修改 结束 ====================
def test_build_url_does_not_duplicate_http_scheme():
    assert build_minio_image_url(
        "http://127.0.0.1:9000",
        "knowledge",
        "images/manual/photo one.jpg",
    ) == "http://127.0.0.1:9000/knowledge/images/manual/photo%20one.jpg"


# ==================== AI修改 开始 ====================
# 验证常见的 host:port 配置也能生成浏览器可以直接访问的 HTTP 地址。
# ==================== AI修改 结束 ====================
def test_build_url_adds_http_for_host_port_endpoint():
    assert build_minio_image_url(
        "127.0.0.1:9000", "knowledge", "img/manual/a.png"
    ) == "http://127.0.0.1:9000/knowledge/img/manual/a.png"


# ==================== AI修改 开始 ====================
# 导入文档可能使用 Markdown 或 HTML 两种图片语法，两种都必须进入统一解析器。
# ==================== AI修改 结束 ====================
def test_extract_supports_markdown_and_html_images():
    text = (
        "![a](https://minio/a.png) "
        '<img src="images/b.jpg" style="zoom: 50%">'
    )
    assert extract_image_references(text) == [
        "https://minio/a.png",
        "images/b.jpg",
    ]


# ==================== AI修改 开始 ====================
# 旧 Milvus 切片里只保存 images/xxx.jpg，需要按文档名映射到新的 MinIO 对象目录。
# ==================== AI修改 结束 ====================
def test_resolve_legacy_relative_reference_uses_document_stem():
    assert resolve_image_reference(
        "images/b.jpg", "manual", "127.0.0.1:9000", "knowledge", "img"
    ) == "http://127.0.0.1:9000/knowledge/img/manual/b.jpg"


# ==================== AI修改 开始 ====================
# 返回前去重，避免同一张图片因多个召回 chunk 被重复渲染。
# ==================== AI修改 结束 ====================
def test_normalize_image_urls_deduplicates_and_ignores_non_images():
    assert normalize_image_urls([
        "http://minio/a.png",
        "http://minio/a.png",
        "http://example.com/readme.txt",
        "images/b.jpg",
    ]) == ["http://minio/a.png", "images/b.jpg"]


# ==================== AI修改 开始 ====================
# 用户明确索要流程图时，最终重排结果可能只有文字说明；
# 还要从本轮召回候选中补抓带图片的切片，才能真正把图展示出来。
# ==================== AI修改 结束 ====================
def test_image_request_collects_images_from_fallback_candidates():
    primary_chunks = [
        {"file_title": "manual", "content": "流程图说明文字，但这里没有图片"}
    ]
    fallback_chunks = [
        {"file_title": "manual", "content": "掌柜智库流程图 ![](images/flow.png)"}
    ]

    assert collect_image_references_from_chunks(
        primary_chunks, fallback_chunks, "给我掌柜智库的流程图"
    ) == ["images/flow.png"]


# ==================== AI修改 开始 ====================
# 测试文件新增逻辑到此结束；每个 URL 规则变化都应先补测试再修改实现。
# ==================== AI修改 结束 ====================


# ==================== AI修改 开始 ====================
# 测试文件新增逻辑到此结束；每个 URL 规则变化都应先补测试再修改实现。
# ==================== AI修改 结束 ====================
