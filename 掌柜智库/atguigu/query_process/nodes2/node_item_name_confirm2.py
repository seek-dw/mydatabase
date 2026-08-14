import json

from langchain.chat_models import init_chat_model

from atguigu.config.config import ModelConfig, MilvusConfig
from atguigu.config.prompt import ITEM_NAME_EXTRACT_SYSTEM_PROMPT, ITEM_NAME_EXTRACT_TEMPLATE
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.bgem3_create_tool import vectorize_texts
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import create_reqs, my_hybrid_search
from atguigu.tool.mongo_client_tool import add_or_update_history, get_recent_history_list, \
    update_item_names_and_rewritten_query


class NodeItemNameConfirm(NodeBase):
    name: str = "node_item_name_confirm"



    def process(self,state:QueryGraphState ):
        """
        1.拿会话id,重写问题
        2.原始问题记录保存到该会话
        3.拿最近10条
        4.遍历,拼接
        5.调用llm,撰写提示词(json),包含拼接好的历史记录和重写问题
        6.解析结果,判断是否json误转并处理
        7.反序列化
        8.从结果中取出意图识别的item_name,rewritten_query
        9.整理一下,去空字符串,原始问题覆盖
        10.向量化意图识别item_name列表
        10.遍历意图识别item_name列表
        11.拿到每一个item的稠密稀疏向量
        12.进入混合搜索 匹配主体识别的向量库
        13.拿到结果,解析结果,添加到字典
        14.extend整理循环所有item搜索结果
        15.对齐,过滤,利用分数进行分层
        16.符合,意图识别成功!,否则进行用户反馈,判断有无answer
        17,answer若在,保存反馈记录,且意图识别成功
        18.answer不存在,意图识别模糊,获取最近10条历史记录,根据id将item_name是[]和rewritten_query覆盖
        :param state:
        :return:
        """
        session_id = state.get("session_id","")
        original_query = state.get("original_query","")
        if not session_id or not original_query:
            logger.info("意图识别节点接收数据错误")
            raise Exception("意图识别节点接收数据错误")

        message_id  = add_or_update_history(session_id = session_id,role = "user",text = original_query)

        history_list = get_recent_history_list(session_id,limit=10)

        history_content = ""
        for history in history_list:
            content =f"{history.get("role","")}:{history.get("text","")}\n"
            history_content+=content

        llm = init_chat_model(
            model = ModelConfig.LLM_MODEL_NAME,
            model_provider="openai",
            api_key = ModelConfig.VL_MODEL_API_KEY,
            base_url = ModelConfig.VL_MODEL_BASE_URL,
            temperature = ModelConfig.VL_MODEL_TEMPERATURE
        )
        messages = [
            {"role":"system","content":ITEM_NAME_EXTRACT_SYSTEM_PROMPT},
            {"role":"user","content":ITEM_NAME_EXTRACT_TEMPLATE.format(
                history_text=history_content,
                original_query=original_query
            )}
        ]
        res = llm.invoke(input = messages)
        print(res.content)
        #提示词里面包含了json解析格式,解析一下结果
        try:
            res_json = res.content
            if res_json.startswith("```json"):
                res_json.replace("```json", "").replace("```","")
            res_dict = json.loads(res_json)
            item_names = res_dict.get("item_names","")
            rewritten_query = res_dict.get("rewritten_query","")
            if item_names:
                item_name_list = [item_name.replace(" ","").replace("\n","").replace("\t","")
                                 for item_name in item_names]
            if not rewritten_query:
                rewritten_query = original_query
        except Exception as e:
            logger.error(e)
            raise e

        embed_item_dict = vectorize_texts(item_name_list)
        all_hyde_search_result = []
        for idx , item_name in enumerate(item_name_list):
            dense_data = embed_item_dict.get("dense","")[idx]
            sparse_data = embed_item_dict.get("sparse","")[idx]

            reqs = create_reqs(
                dense_data = dense_data ,
                sparse_data = sparse_data,
                dense_anns_field = "dense_vector",
                sparse_anns_field = "sparse_vector",
                dense_param= {
                    "metric_type": "COSINE"
                },
                sparse_param = {
                    "metric_type": "IP"
                }
            )
            res = my_hybrid_search(
                reqs = reqs,
                collection_name = MilvusConfig.milvus_item_collection,
                ranker = (0.9,0.1),
                limit = 10,
                output_fields = ["item_name"]
            )
            hyde_search_result = [{
                "original_item_name":item_name,
                "hyde_search_itme_name":item.get("entity",{}).get("item_name",""),
                "score":item.get("distance","")
            } for item in res[0]]
            all_hyde_search_result.extend(hyde_search_result)
            # print(all_hyde_search_result)

        confirm_item_names = [item.get("hyde_search_item_name")for item in all_hyde_search_result
                            if item.get("score")>=0.9]
        option_item_names = [item.get("hyde_search_item_name") for item in all_hyde_search_result
                             if item.get("score")<0.9 or item.get("score")>0.6]
        if confirm_item_names:
            final_item_name = confirm_item_names
            answer = ""
        elif option_item_names:
            final_item_name = []
            answer = f"请确认您要咨询的商品是哪一个{','.join(option_item_names)}"
        else:
            final_item_name = []
            answer = "无法识别您要咨询的商品,请重新提问"

        if answer:
            add_or_update_history(session_id,role="assistant",text=answer)
        history_list = get_recent_history_list(session_id,limit=10)
        ids = [history.get("_id","") for history in history_list]
        if ids:
           update_item_names_and_rewritten_query(ids,item_name = final_item_name,rewritten_query=rewritten_query)

        return {
            "answer":answer,
            "item_names":final_item_name,
            "rewritten_query":rewritten_query,
            "history":get_recent_history_list(session_id,limit = 10),
            "message_id":message_id,
            "original_query":original_query
        }


if __name__ == '__main__':
    session_id = "test_001"
    add_or_update_history(session_id, "user", "咨询下烫金机。")
    add_or_update_history(session_id, "assistant", "您好。请问是哪个型号")
    add_or_update_history(session_id, "user", "hak180")
    add_or_update_history(session_id, "assistant", "具体有什么问题呢？")
    node = NodeItemNameConfirm()
    init_state = {
        "session_id": 1,
        "original_query": "如何购买ipad"
    }
    res = node(init_state)
    logger.info(convert_to_json(res))
