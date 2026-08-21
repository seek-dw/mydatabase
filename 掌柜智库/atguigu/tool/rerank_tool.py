import os
import requests
#调用官方API文档,本质上都是给云端模型发送请求,填写参数即可
from atguigu.config.config import ModelConfig
# ==================== AI修改 开始 ====================
# 慢/崩链路修复: 原来 timeout=5 + except raise —— 云端rerank一次重排几十个长文档
# 经常3-5秒, 网络稍差就超时抛异常, 整个回答链路直接失败。
# 改进:
#   1. timeout 5 -> 12: 给云端留足处理时间, 减少误超时
#   2. 失败不 raise, 返回空列表: node_rerank 拿到空结果后 score 保持原值,
#      排序退化为 RRF 原顺序 —— 链路永不因 rerank 失败而崩
# ==================== AI修改 结束 ====================
def rerank(query,texts,limit=10):
    try:
        url = "https://openrouter.ai/api/v1/rerank"
        headers = {
            "Authorization": f"Bearer {ModelConfig.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free",
            "query": query,
            "documents": texts,
            "return_documents": True,
            "top_n": limit
        }

        response = requests.post(url, json=payload, headers=headers,timeout=12)
        if response.status_code == 200:
            return [{"index":res.get("index"),
                     "score":res.get("relevance_score")}
                    for res in response.json().get("results")]
        else:
            # 非200也降级(返回空), 不 raise
            from atguigu.tool.logger import logger
            logger.error(f"rerank API 返回非200: {response.status_code} {response.text[:200]}")
            return []

    except Exception as e:
        # 降级: 返回空列表, 由调用方按原顺序继续(不崩链路)
        from atguigu.tool.logger import logger
        logger.error(f"rerank 调用失败, 降级为原顺序: {e}")
        return []

if __name__ == '__main__':
    print(rerank("你是谁", ["你是谁", "我是AI", "我是机器人"], 2))