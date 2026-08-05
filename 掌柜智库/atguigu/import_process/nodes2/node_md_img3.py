import base64
import os
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model

from atguigu.config.config import ModelConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodeMDImg(NodeBase):


    name = "node_md_img"
    def process(self,state:ImportGraphState):
        md_path = state.get("md_path","")
        if not md_path:
            logger.error("上传路径错误")
            raise Exception("上传路径错误")
        md_path_obj = Path(md_path)
        if not md_path_obj:
            logger.error("上传目录不存在")
            raise Exception("上传目录不存在")

        with open(md_path_obj,"r",encoding="utf-8") as f:
            md_content = f.read()
            if not md_content:
                logger.error("文件内容为空")
                return md_content
        images_dir_path_obj = md_path_obj.parent / "images"
        if not images_dir_path_obj.exists():
            logger.error("该目录不存在")
            return md_content

        every_image_path_list = os.listdir(images_dir_path_obj)
        if not every_image_path_list:
            logger.error("该目录为空")
            return {"md_content":md_content}

        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        length = 200
        every_image_context_path_list =  []
        for every_image_path in every_image_path_list:
            if Path(every_image_path).suffix.lower() not in image_extensions:
                logger.error(f"{every_image_path}图片格式不支持")
                continue
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(every_image_path) + r"\)")
            match = pattern.search(md_content)
            if not match:
                logger.error(f"{every_image_path}图片未被引用")
                continue
            start ,end  = match.span()
            pre_text = md_content[max((start - length),0):start]
            follow_text = md_content[end:min(len(md_content),(end+length))]

            every_single_image_path = images_dir_path_obj / every_image_path

            with open(every_single_image_path,"rb") as f:
                every_image_data  = f.read()

                every_image_base64_str = base64.b64encode(every_image_data).decode("utf-8")
                every_image_context_path_list.append(
                    {
                        "every_image_base64_str":every_image_base64_str,
                        "pre_text":pre_text,
                        "follow_text":follow_text,
                        "every_single_image_path":every_single_image_path

                    }


                )

        dq =deque(maxlen = 20)
        llm = None
        summary_list = []
        for every_image_context_path in every_image_context_path_list:
            current_time = time.time()
            while dq and current_time - dq[0] > 60:
                dq.popleft()
            if len(dq) == dq.maxlen:
                need_wait_time = 60  - (current_time-dq[0])
                if need_wait_time > 0 :
                    time.sleep(need_wait_time)
                    current_time = time.time()
                    while dq and current_time - dq[0] > 60:
                        dq.popleft()
            dq.append(current_time)

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式就是base64在使用的时候的规定
                                "url": "data:image/jpeg;base64," + every_image_base64_str,
                            },
                        },
                        {"type": "text", "text": f"""
                                                               这是一张图片，图片上文部分为"{every_image_context_path.get("pre_text")}"，
                                                               下文部分为"{every_image_context_path.get("follow_text")}"，
                                                               请用中文简要总结这张图片的摘要,字数在50字以内。"""
                         },
                    ],
                },
            ]
            if not llm:
                llm = init_chat_model(
                    model=ModelConfig.qwen3vl_model_name,
                    model_provider="openai",
                    api_key=ModelConfig.qwen3vl_api_key,
                    base_url=ModelConfig.qwen3vl_base_url,
                    temperature=ModelConfig.qwen3vl_model_temperature
                )

            res = llm.invoke(input = messages)

            summary_list.append(
                {
                    "image_name": every_image_context_path.get("every_image_path_list"),
                    "image_single_path": every_image_context_path.get("every_single_image_path"),
                    "summary": res.content
                }

            )

        return summary_list



if __name__ == '__main__':
    node = NodeMDImg()
    init_state = {
        "md_path": r"C:\Users\Administrator\Desktop\gitee\my_project\hak180产品安全手册\hak180产品安全手册.md"
    }
    res = node(init_state)
    logger.info(res)
