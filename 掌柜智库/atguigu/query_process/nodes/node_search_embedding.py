# atguigu/query_process/nodes/node_search_embedding.py
import json

from atguigu.config.config import MilvusConfig
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.bgem3_create_tool import vectorize_texts
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import create_reqs, my_hybrid_search


class NodeSearchEmbedding(NodeBase):
    """
    节点功能：基于已确认主体名+改写后的用户问题，执行Milvus向量数据库混合检索
    实现思路:
        1.item_names,rewritten_query二者不为空,说明有值,说明answer为空,
        需要根据重写的问题和意图识别进行多路搜索,这是第一个向量搜索
        2.根据二者进行向量搜索,拿到自己需要的向量库的数据和字段
        3.将数据整理成统一的key方便后续rrf倒排融合

    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_search_embedding"

    def process(self, state: QueryGraphState):
        # 拿到上一轮的意图识别和改写后的用户问题
        rewritten_query = state.get("rewritten_query", "")
        item_names = state.get("item_names", "")
        if not rewritten_query or not item_names:
            logger.info("向量搜索节点接收意图识别数据失败")
            raise Exception("向量搜索节点接收意图识别数据失败")

        # 虽然只有一个rewritten_query ,但是vectorize_texts函数需要列表
        embed_query = vectorize_texts([rewritten_query])
        # 获取重写的问题的稀疏稠密
        dense_data = embed_query.get("dense")[0]
        sparse_data = embed_query.get("sparse")[0]
        # 拿到要检索的表名
        collection_name = MilvusConfig.milvus_chunks_collection

        # 开始检索,首先创建混合检索请求
        # expr过滤字段需要字符串,所以item_names需要整理将里面的特殊字符转义
        # (意图识别出来的item_names经过item_name向量库匹配搜索到的所有主体识别名称)
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

        embedding_chunks = [
            {
                #把entity解包得到所有的output_fields
                **search_result.get("entity",{}),
                "score":search_result.get("distance"),
                "source":"local"
            }
            for search_result in res[0]
        ]

        return {
            "embedding_chunks":embedding_chunks
        }

if __name__ == '__main__':
    init_state = {
        "rewritten_query":"关于HAK180烫金机如何使用",
        "item_names":["HAK180烫金机"]
    }
    node = NodeSearchEmbedding()
    res = node(init_state)
    logger.info(convert_to_json(res))