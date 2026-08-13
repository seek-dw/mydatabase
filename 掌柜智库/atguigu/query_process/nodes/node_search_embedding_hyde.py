# atguigu/query_process/nodes/node_search_embedding_hyde.py
import json

from langchain.chat_models import init_chat_model

from atguigu.config.config import ModelConfig, MilvusConfig
from atguigu.config.prompt import HYDE_PROMPT
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.bgem3_create_tool import vectorize_texts
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import create_reqs, my_hybrid_search


class NodeSearchEmbeddingHyde(NodeBase):
    """
    节点功能：HyDE (Hypothetical Document Embedding)
    先让 LLM 生成假设性答案，再对答案进行向量检索，提高召回率。
    实现思路:
        1.拿到item_name和rewritten_query之后判断并校验
        2.交给llm生成假设性答案
        3.将rewritten_query再次重写
        4.送入向量库查询得到搜索结果
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_search_embedding_hyde"

    def process(self, state: QueryGraphState):
        #校验
        item_names = state.get("item_names","")
        rewritten_query = state.get("rewritten_query","")
        if not item_names or not rewritten_query:
            logger.error("向量搜索节点接收意图识别数据失败")
            raise Exception("向量搜索节点接收意图识别数据失败")

        #生成假设性答案
        llm = init_chat_model(
            model = ModelConfig.LLM_MODEL_NAME,
            model_provider = "openai",
            api_key = ModelConfig.VL_MODEL_API_KEY,
            base_url = ModelConfig.VL_MODEL_BASE_URL,
            temperature = ModelConfig.VL_MODEL_TEMPERATURE
        )

        messages = [{
            "role":"user","content":HYDE_PROMPT.format(rewritten_query= rewritten_query)
        }]

        res = llm.invoke(input = messages)
        #Hypothetical Document Embeddings 假设性文档嵌入
        hyde_answer = res.content
        #重写rewritten_query
        merge_query = f"{rewritten_query}/{hyde_answer}"




        #向量化问题,进行混合搜索
        embed_query = vectorize_texts([merge_query])
        dense_data = embed_query.get("dense")[0]
        sparse_data = embed_query.get("sparse")[0]
        # 开始检索,首先创建混合检索请求
        # expr过滤字段需要字符串,所以item_names需要整理将里面的特殊字符转义
        # (意图识别出来的item_names经过item_name向量库匹配搜索到的所有主体识别名称)
        collection_name = MilvusConfig.milvus_chunks_collection

        item_names = [
            item.replace("\\", "\\\\").replace("'", "\'").replace('"', "\"")
            for item in item_names
        ]
        reqs = create_reqs(
            dense_data=dense_data,
            sparse_data=sparse_data,
            dense_anns_field="dense_vector",
            sparse_anns_field="sparse_vector",
            dense_param={
                "metric_type": "COSINE"
            },
            sparse_param={
                "metric_type": "IP"
            },
            expr=f"item_name in {json.dumps(item_names)}"
        )

        res = my_hybrid_search(
            collection_name=collection_name,
            reqs=reqs,
            ranker=[0.9, 0.1],
            output_fields=["id", "title", "file_title", "content", "item_name"],
            limit=10
        )
        # print(convert_to_json(res))

        hyde_embedding_chunks = [
            {
                # 把entity解包得到所有的output_fields
                **search_result.get("entity", {}),
                "score": search_result.get("distance"),
                "source": "local"
            }
            for search_result in res[0]
        ]

        return {
            "hyde_embedding_chunks": hyde_embedding_chunks
        }



if __name__ == '__main__':
    init_state = {
        "rewritten_query": "关于HAK180烫金机如何使用",
        "item_names": ["HAK180烫金机"]
    }
    node = NodeSearchEmbeddingHyde()
    res = node(init_state)
    logger.info(convert_to_json(res))