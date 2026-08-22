"""语言模型和视觉模型的平台切换回归测试。"""

from pathlib import Path


# ==================== AI修改 开始 ====================
# OpenRouter/魔搭切换必须由一个环境变量决定，不能要求修改业务节点代码。
# ==================== AI修改 结束 ====================
def test_openrouter_profile_uses_dots_for_text_and_vision():
    from atguigu.config.config import resolve_model_profiles

    config = resolve_model_profiles(
        {
            "MODEL_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "openrouter-key",
        }
    )

    assert config["provider"] == "openrouter"
    assert config["llm_model"] == "dots-studio/dots-3-note-preview:free"
    assert config["vl_model"] == "dots-studio/dots-3-note-preview:free"
    assert config["llm_api_key"] == "openrouter-key"
    assert config["vl_api_key"] == "openrouter-key"
    assert config["llm_base_url"] == "https://openrouter.ai/api/v1"
    assert config["vl_base_url"] == "https://openrouter.ai/api/v1"


# ==================== AI修改 开始 ====================
# 保留原有环境变量命名，切回魔搭时不要求用户重写已有模型配置。
# ==================== AI修改 结束 ====================
def test_modelscope_profile_keeps_legacy_environment_variables():
    from atguigu.config.config import resolve_model_profiles

    config = resolve_model_profiles(
        {
            "MODEL_PROVIDER": "modelscope",
            "MODA_API_KEY": "modelscope-key",
            "VL_MODEL_BASE_URL": "https://api-inference.modelscope.cn/v1",
            "LLM_MODEL_NAME": "modelscope-text",
            "VL_MODEL_NAME": "modelscope-vision",
        }
    )

    assert config["provider"] == "modelscope"
    assert config["llm_model"] == "modelscope-text"
    assert config["vl_model"] == "modelscope-vision"
    assert config["llm_api_key"] == "modelscope-key"
    assert config["vl_api_key"] == "modelscope-key"
    assert config["llm_base_url"] == "https://api-inference.modelscope.cn/v1"
    assert config["vl_base_url"] == "https://api-inference.modelscope.cn/v1"


# ==================== AI修改 开始 ====================
# 活动节点必须按模型类型读取独立配置；重排序链路不纳入本次切换。
# ==================== AI修改 结束 ====================
def test_active_nodes_use_selected_text_or_vision_configuration():
    root = Path(__file__).parents[1] / "atguigu"
    text_nodes = [
        root / "query_process" / "nodes" / "node_answer_output.py",
        root / "query_process" / "nodes" / "node_item_name_confirm.py",
        root / "query_process" / "nodes" / "node_search_embedding_hyde.py",
        root / "import_process" / "nodes" / "node_item_name_recognition.py",
    ]
    vision_nodes = [root / "import_process" / "nodes" / "node_md_img.py"]

    for path in text_nodes:
        source = path.read_text(encoding="utf-8")
        assert "ModelConfig.LLM_API_KEY" in source
        assert "ModelConfig.LLM_BASE_URL" in source

    for path in vision_nodes:
        source = path.read_text(encoding="utf-8")
        assert "ModelConfig.VL_API_KEY" in source
        assert "ModelConfig.VL_BASE_URL" in source


# ==================== AI修改 开始 ====================
def test_model_config_exposes_vision_base_url_used_by_image_node():
    from atguigu.config.config import ModelConfig

    assert ModelConfig.VL_BASE_URL == ModelConfig.VL_MODEL_BASE_URL
    assert ModelConfig.VL_BASE_URL


# ==================== AI修改 结束 ====================


# ==================== AI修改 开始 ====================
# 余额/额度错误无法靠等待恢复，不能被 429 判断误识别为可重试限流。
# ==================== AI修改 结束 ====================
def test_balance_errors_are_not_retryable_but_rate_limits_are():
    from atguigu.import_process.nodes.node_md_img import is_retryable_rate_error

    assert not is_retryable_rate_error("Error code: 429 insufficient balance")
    assert not is_retryable_rate_error("insufficient_quota")
    # ==================== AI修改 开始 ====================
    assert not is_retryable_rate_error(
        "429 Rate limit exceeded: free-models-per-day"
    )
    assert not is_retryable_rate_error(
        "429 openrouter_free_tier_daily: daily reset"
    )
    # ==================== AI修改 结束 ====================
    assert is_retryable_rate_error("429 Too Many Requests")
    assert is_retryable_rate_error("TPM rate limit exceeded")
