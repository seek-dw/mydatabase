import os
import requests
#调用官方API文档,本质上都是给云端模型发送请求,填写参数即可
from atguigu.config.config import ModelConfig
def rerank(query,texts,limit=10):
    try:
        url = "https://api.siliconflow.cn/v1/rerank"
        headers = {
            "Authorization": f"Bearer {ModelConfig.VL_MODEL_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "Qwen/Qwen3-VL-Reranker-8B",
            "query": query,
            "documents": texts,
            "return_documents": True,
            "top_n": limit
        }

        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return [{"index":res.get("index"),
                     "score":res.get("relevance_score")}
                    for res in response.json().get("results")]

    except Exception as e:
        raise e

if __name__ == '__main__':
    print(rerank("你是谁", ["你是谁", "我是AI", "我是机器人"], 2))