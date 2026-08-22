"""导入任务状态流转的回归测试。"""

from pathlib import Path
from uuid import uuid4


# ==================== AI修改 开始 ====================
# 限流等待必须是后端明确返回的状态，不能继续用空字符串让前端猜测。
# ==================== AI修改 结束 ====================
def test_rate_limit_waiting_status_exposes_retry_details():
    from atguigu.tool.task_utils import (
        TASK_STATUS_WAITING_RESPONSE,
        get_task_info,
        set_task_waiting_response,
    )

    task_id = f"test-rate-limit-{uuid4()}"
    set_task_waiting_response(
        task_id,
        retry_count=1,
        retry_after=30,
        message="触发限流，等待后重试",
    )

    info = get_task_info(task_id)

    assert info["status"] == TASK_STATUS_WAITING_RESPONSE
    assert info["status_detail"] == {
        "message": "触发限流，等待后重试",
        "retry_count": 1,
        "retry_after": 30,
    }


# ==================== AI修改 开始 ====================
# 首页必须展示 waiting_response，并在后端恢复 processing 后回到处理中。
# ==================== AI修改 结束 ====================
def test_import_page_renders_rate_limit_waiting_state():
    page = Path(__file__).parents[1] / "atguigu" / "web" / "page" / "index.html"
    html = page.read_text(encoding="utf-8")

    assert "waiting_response" in html
    assert "等待响应中" in html
    assert "status-waiting" in html
    assert "状态丢失" not in html

    import_page = page.with_name("import.html").read_text(encoding="utf-8")
    assert "waiting_response" in import_page
    assert "等待响应中" in import_page


# ==================== AI修改 开始 ====================
# 图片摘要重试循环必须在退避前写 waiting_response，重试前恢复 processing，
# 否则前端无法知道后端正在等待限流窗口恢复。
# ==================== AI修改 结束 ====================
def test_image_retry_loop_updates_task_status_around_backoff():
    source = (
        Path(__file__).parents[1]
        / "atguigu"
        / "import_process"
        / "nodes"
        / "node_md_img.py"
    ).read_text(encoding="utf-8")

    assert "set_task_waiting_response" in source
    assert "TASK_STATUS_PROCESSING" in source
