# atguigu/query_process/nodes/node_answer_output.py
import re

from langchain.chat_models import init_chat_model

from atguigu.config.config import ModelConfig
from atguigu.config.prompt import ANSWER_PROMPT
from atguigu.query_process.base import NodeBase
from atguigu.query_process.state import QueryGraphState
from atguigu.tool.logger import logger
from atguigu.tool.mongo_client_tool import add_or_update_history
from atguigu.tool.task_utils import put_data


class NodeAnswerOutput(NodeBase):
    """
    节点功能: 答案生成
    """

    # 覆盖基类的 name 属性，标识节点名称
    name: str = "node_answer_output"

    def process(self, state: QueryGraphState):
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """
        # 1.拿到answer,根据answer有无进行下一步的判断
        # question 为什么? 有answer 不是再给用户反馈吗,这不能算作最终的answer吧
        answer = state.get("answer")
        task_id = state.get("task_id")
        if answer:
            put_data(task_id, "final", {"answer": answer})
        else:
            chunks = state.get("reranked_docs") or []
            chunk_content = ""
            for chunk in chunks:
                title = chunk.get("title")
                content = chunk.get("content")
                url = chunk.get("url")
                source = chunk.get("source")
                content = f"[{title}] [{url}] [{source}]\n{content}\n\n"
                chunk_content += content

            history = state.get("history") or []
            history_content = ""
            for h in history:
                h_content = f"{h.get('role', '')}: {h.get('text', '')}\n\n"
                history_content += h_content

            item_names = state.get("item_names") or []
            item_names_str = ",".join(item_names)

            rewritten_query = state.get("rewritten_query")
            prompt = ANSWER_PROMPT.format(
                context = chunk_content,
                history = history_content,
                question = rewritten_query,
                item_names = item_names_str
            )

            #question 大模型一次接收的最大长度一般是多少,如果吧问题截掉了没事吗?
            if len(prompt) > 10000:
                prompt = prompt[:10000]

            #调用大模型
            llm = init_chat_model(
                model = ModelConfig.LLM_MODEL_NAME,
                model_provider="openai",
                api_key = ModelConfig.VL_MODEL_API_KEY,
                base_url = ModelConfig.VL_MODEL_BASE_URL,
                temperature = ModelConfig.VL_MODEL_TEMPERATURE
            )

            messages = [
                {
                    "role":"user","content":prompt
                }
            ]
            #流式调用,返回生成器
            res = llm.stream(input = messages)
            answer = ""
            for r in res:
                delta = r.content or ""
                if delta:
                    put_data(task_id, "delta", {"delta": delta})
                    answer += delta

            #处理图片,吧图片的urls也返回到前端
            seen = set() #去重
            #question 为什么这里小括号(())不应该是一对吗
            md_img_pattern = re.compile(r'!\[.*?\]\((.*?)\)')
            for i, doc in enumerate(chunks):
                text = doc.get("content") or ""
                matches = md_img_pattern.findall(text)
                for img_url in matches:
                    img_url = img_url.strip()
                    if img_url and img_url not in seen:
                        seen.add(img_url)
            images = list(seen)

            #保存历史
            if answer:
                session_id = state.get("session_id")
                add_or_update_history(
                    session_id = session_id,
                    role = "assistant",
                    text = answer,
                    rewritten_query = rewritten_query,
                    item_names = item_names,
                    image_urls = images
                )
            put_data(task_id,"final",{"image_urls":images})
        return {
            "answer":answer
        }


