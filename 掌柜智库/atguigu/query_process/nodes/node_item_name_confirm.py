# atguigu/query_process/nodes/node_item_name_confirm.py

import json
import re
from typing import Any
from langchain.chat_models import init_chat_model
from atguigu.config.config import ModelConfig, MilvusConfig
from atguigu.config.prompt import ITEM_NAME_EXTRACT_SYSTEM_PROMPT, ITEM_NAME_EXTRACT_TEMPLATE
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.bgem3_create_tool import vectorize_texts
from atguigu.tool.logger import logger
from atguigu.tool.milvus_client_create import create_reqs, my_hybrid_search
from atguigu.tool.mongo_client_tool import add_or_update_history, get_recent_history_list,update_item_names_and_rewritten_query


class NodeItemNameConfirm(NodeBase):
    """
    节点功能：确认用户问题中的核心商品名称
    实现思路:
        1.获取最近的10条历史会话记录,整理成一个字符串
        2.交给大模型进行产品名称确认,并重写用户问题
        3.将大模型返回的产品名称确认向量化并匹配主体识别向量库进行混合检索
        4.拿到原始商品名称,模型确认商品名称,以及匹配的分数,根据是否存在,以及分数大小,决定是否替换用户问题中的商品名称
        5.如果替换,在历史记录中更新意图识别以及问题重写
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_item_name_confirm"

    def process(self, state: QueryGraphState):
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """
        # 一.获取最近的10条历史会话记录,整理成一个字符串
        history_content, message_id, original_query, session_id = self.make_history_to_str(state)
        # 二.交给大模型进行产品名称确认,并判断输出结果格式,并进行解析拿到item_name和rewritten_query
        item_name_list, rewritten_query = self.send_to_llm_and_parse_item_name(history_content, original_query)
        # 三.意图识别item_name匹配混合搜索主体识别,拿到{意图item_name,主体item_name,匹配分数}
        all_searched_item_name_list = self.item_match_and_get_all_search_item_list(item_name_list)
        # 四.对齐和过滤:根据匹配的分数, 根据是否存在, 以及分数大小, 决定最终返回的item_name以及answer变量,判断是否反馈给用户需要确认
        answer, final_item_names = self.align_and_filter_for_distance(all_searched_item_name_list)
        # 五.保存反馈历史,以及回填最近10条历史记录 IMPROVE限制了只能在一个会话窗口问一种问题,否则会污染历史
        message_id = self.judge_answer_and_backfill_history(answer, final_item_names, message_id, rewritten_query,session_id)


        return {
            "message_id":message_id,#反馈信息的id
            "original_query":original_query,#原始问题
            "rewritten_query":rewritten_query,#重写的问题
            "item_names":final_item_names,#最终确定的商品名称
            "answer":answer,#反馈信息
            "history":get_recent_history_list(session_id,limit=10)#历史记录
        }

    def make_history_to_str(self, state: QueryGraphState) -> tuple[str, str, str, Any]:


        # 要进入该节点,说明用户已经提问,所以已经有了历史记录,所以拿去session_id以及原始问题origin_query
        session_id = state.get("session_id", "")
        if not session_id:
            logger.error("session_id 不存在")
            raise Exception("session_id 不存在")
        original_query = state.get("original_query", "")
        if not original_query:
            logger.error("用户原始问题不存在")
            raise Exception("用户原始问题不存在,请输入您的问题")

        # 将该问题存入历史记录,返回的是InsertOne的inserted_id也就是mongo自动生成的_id
        message_id = add_or_update_history(session_id, "user", original_query)

        # 从当前session_id中抽取前10条历史消息进行llm意图识别的原料,IMPROVE 局限性很高,换个窗口历史就是0
        history_list = get_recent_history_list(session_id=session_id, limit=10)

        history_content = ""
        for history in history_list:
            # 从history取出要给大模型意图识别的内容,这里取"role","text"
            content = f"{history.get("role", "")}:{history.get("text", "")}\n"
            # 字符串拼接
            history_content += content
        return history_content, message_id, original_query, session_id

    def send_to_llm_and_parse_item_name(self, history_content: str, original_query: str) -> tuple[list[Any], Any]:

        #     IMPROVE 每次运行都要重新初始化
        llm = init_chat_model(
            model=ModelConfig.LLM_MODEL_NAME,
            model_provider="openai",
            api_key=ModelConfig.VL_MODEL_API_KEY,
            base_url=ModelConfig.VL_MODEL_BASE_URL,
            temperature=ModelConfig.VL_MODEL_TEMPERATURE
        )
        messages = [
            {"role": "system", "content": ITEM_NAME_EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": ITEM_NAME_EXTRACT_TEMPLATE.format(
                history_text=history_content,
                original_query=original_query)
             }]

        res = llm.invoke(input=messages)
        # 拿到大模型的意图识别,结果格式不可控,使用try模块定位异常
        try:
            res_json = res.content
            # 如果输出的是markdown格式的json,将其转化为
            if res_json.startswith("```json"):
                res_json = res_json.replace("```json", "").replace("```", "")
            # 反序列化
            res_dict = json.loads(res_json)
            # 拿到意图识别和重写问题
            item_names = res_dict.get("item_names")
            rewritten_query = res_dict.get("rewritten_query")
            # 判断意图识别是否存在,如果存在转换为列表
            if item_names:
                item_name_list = [item_name.replace(" ", "").replace("\n", "").replace("\t", "")
                                  for item_name in item_names]
            else:
                item_name_list = []
            # 判断rewritten_query是否存在,如果不存在,就是原始问题覆盖
            if not rewritten_query:
                rewritten_query = original_query
        except Exception as e:
            logger.error("模型输出格式异常", e)
            raise e
        return item_name_list, rewritten_query

    def item_match_and_get_all_search_item_list(self, item_name_list: list[Any]) -> list[Any]:
        # 1.将准备好的意图识别列表向量化,返回的是一个字典列表,{"dense":[[],[],[]],"sparse":[[],[],[]]}
        embed_item_dict = vectorize_texts(item_name_list)
        # print(embed_item_dict)
        collection_name = MilvusConfig.milvus_item_collection

        all_searched_item_name_list = []
        # 遍历意图识别列表,并取出每一个的稠密和稀疏向量
        for idx, item_name in enumerate(item_name_list):
            dense_data = embed_item_dict.get("dense")[idx]
            sparse_data = embed_item_dict.get("sparse")[idx]
            # 准备好了query向量,准备混合搜索
            reqs = create_reqs(
                dense_data=dense_data,
                sparse_data=sparse_data,
                dense_anns_field="dense_vector",
                sparse_anns_field="sparse_vector",
                dense_param={"metric_type": "COSINE"},
                sparse_param={"metric_type": "IP"}
            )

            res = my_hybrid_search(
                collection_name=collection_name,
                reqs=reqs,
                ranker=(0.6, 0.4),
                limit=10,
                output_fields=["item_name"]
            )
            # print(convert_to_json(res))
            # 混合搜索的结果是一个二维列表,
            # data: [[{'id': 468284006386632269, 'distance': 0.3981636166572571, 'entity': {'item_name': 'HAK180烫金机'}}]]
            # res[0]取到一个意图识别的数据,是一个列表字典,里面包含了多个字典,代表一个意图识别里面的多个匹配,id 不同,得分不同
            # searched_item_names 是一个列表字典,里面包含多个字典
            search_item_names = [{
                "original_item_name": item_name,
                "search_item_name": item.get("entity", {}).get("item_name", ""),
                "score": item.get("distance")
            } for item in res[0]]
            # extend,将所有循环的列表字典拆出来一个个字典添加到searched_item_name_list中
            all_searched_item_name_list.extend(search_item_names)
        return all_searched_item_name_list

    def align_and_filter_for_distance(self, all_searched_item_name_list: list[Any]) -> tuple[str, list[Any]]:
        # 拿到所有意图识别的匹配item_name以及评分,接下来对齐过滤
        # 确定没问题的搜索结果,可以直接用
        confirm_item_names = [
            item.get("search_item_name") for item in all_searched_item_name_list
            if item.get("score") >= 0.8
        ]
        # 模糊结果,得分不高不低,需要用户确认
        option_item_names = [
            item.get("search_item_name") for item in all_searched_item_name_list
            if item.get("score") >= 0.5 and item.get("score") < 0.8
        ]
        # 如果存在则赋值给最终的item_name
        if confirm_item_names:
            final_item_names = confirm_item_names
            answer = ""
        elif option_item_names:
            final_item_names = [] #question 这里item为啥为空?只能为空?
            answer = f"请确认您要咨询的商品是哪一个{','.join(option_item_names)}"
        else:
            final_item_names = []
            answer = "无法识别您咨询的问题,请重新提问"

        # 判断answer有没有值来处理历史记录
        # 如果answer有值,则代表向用户反馈了信息,则会存在历史记录,要添加历史记录
        # 如果没有,则证明意图识别匹配到了高分答案,直接输出,不添加历史记录
        # 不管有没有,最好都要重新更新item_names和rewritten_query
        return answer, final_item_names

    def judge_answer_and_backfill_history(self, answer: str, final_item_names: list[Any], message_id, rewritten_query,session_id) -> Any:
        if answer:
            # 保存这个反馈信息到历史记录中
            message_id = add_or_update_history(session_id, "assistant", answer)
        # QUESTION查询10条历史记录,为啥取10条?这样回填不会污染历史?为什么不是根据message_id更新
        history_list = get_recent_history_list(session_id, limit=10)
        ids = [history.get("_id") for history in history_list]
        if ids:
            update_item_names_and_rewritten_query(ids, item_names=final_item_names, rewritten_query=rewritten_query)
        return message_id




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
