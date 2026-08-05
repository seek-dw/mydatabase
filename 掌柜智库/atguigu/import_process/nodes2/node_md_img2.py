import base64
import os
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model
from minio.deleteobjects import DeleteObject

from atguigu.config.config import ModelConfig, MinioConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger
from atguigu.tool.minio_client_tool import create_minio_client


class NodeMDImg(NodeBase):
    name = "node_md_img"

    # 1.防御 - 判断文件路径 - 判断文件内容
    # 2.构造图片目录,列出目录下所有图片
    # 3.判断图片是否符合图片后缀,利用正则匹配拿到每一个图片的跨度索引
    # 4.拿到跨度索引,切片拿到上下文
    # 5.利用图片路径通过base64拿到图片的字符串表示
    # 6.上下文和表示丢给大模型,考虑限频,使用滑动窗口算法

    def process(self, state: ImportGraphState):
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("路径不存在")
            raise Exception("请提供md文件路径")

        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("路径错误")
            raise Exception("请提供正确的md文件路径")

        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
            if not md_content:
                logger.error("md文件内容为空")
                raise Exception("文件内容为空")

        image_dir_path = md_path_obj.parent / "images"
        if not image_dir_path.exists():
            logger.error("图片目录不存在")
            raise Exception("请提供正确的图片目录")

        every_image_list = os.listdir(image_dir_path)
        if not every_image_list:
            logger.error("图片目录为空")
            raise Exception("请提供正确的图片目录")

        image_context_str_list = []
        length = 200
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        for image_name in every_image_list:
            if Path(image_name).suffix.lower() not in image_extensions:
                logger.error("图片格式错误")
                continue

            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r"\)")

            match = pattern.search(md_content)
            if not match:
                logger.error("图片未找到")
                continue

            start, end = match.span()

            pre_text = md_content[max(0,(start - length)):start]
            follow_text =md_content[end:min(len(md_content),(end + length))]

            single_image_path = image_dir_path / image_name

            with open(single_image_path, "rb") as f:
                image_content = f.read()
            #base64
            every_image_base64_str = base64.b64encode(image_content).decode("utf-8")

            image_context_str_list.append(
                {
                    "pre_text": pre_text,
                    "follow_text": follow_text,
                    "image_base64_str": every_image_base64_str,
                    "single_image_path": single_image_path,
                    "image_name": image_name,
                }
            )
        md_summary_list=[]
        dq = deque(maxlen =200)
        llm = None
        for image_context_str in image_context_str_list:
            current_time = time.time()
            while dq and current_time - dq[0] >60:
                dq.popleft()
            if len(dq) == dq.maxlen:
                need_wait_time = 60 - (current_time - dq[0])
                if need_wait_time > 0 :
                    time.sleep(need_wait_time)
                    current_time = time.time()
                    while dq and current_time - dq[0] >60:
                        dq.popleft()
            dq.append(current_time)

            messages =  [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式就是base64在使用的时候的规定
                                "url": "data:image/jpeg;base64," + image_context_str.get("image_base64_str"),
                            },
                        },
                        {"type": "text", "text": f"""
                                                    这是一张图片，图片上文部分为"{image_context_str.get("pre_text")}"，
                                                    下文部分为"{image_context_str.get("follow_text")}"，
                                                    请用中文简要总结这张图片的摘要,字数在50字以内。"""
                         },
                    ],
                },
            ]
            if not llm:
                llm = init_chat_model(
                    model = ModelConfig.qwen3vl_model_name,
                    model_provider = "openai",
                    api_key = ModelConfig.qwen3vl_api_key,
                    base_url = ModelConfig.qwen3vl_base_url,
                    temperature = ModelConfig.qwen3vl_model_temperature
                )

            res = llm.invoke(input = messages)

            md_summary_list.append(
                {
                    "summary":res.content,
                    "single_image_path":image_context_str.get("single_image_path"),
                    "image_name": image_context_str.get("image_name"),
                }
            )
        upload_dir = "upload-images"
        minio_client = create_minio_client()
        old_image_list = minio_client.list_objects(bucket_name=MinioConfig.MINIO_BUCKET_NAME, prefix=upload_dir, recursive=True)
        errors = minio_client.remove_objects(bucket_name=MinioConfig.MINIO_BUCKET_NAME, delete_object_list=[DeleteObject(old_image.object_name) for old_image in old_image_list])
        for error in errors:
            logger.error(error)
        image_with_summary_and_url_list=[]
        for md_summary in md_summary_list:
            minio_client.fput_object(
                bucket_name=MinioConfig.MINIO_BUCKET_NAME,
                object_name=upload_dir+ "/" + md_summary.get("image_name"),
                file_path=md_summary.get("single_image_path"),
            )
            url = f"http://{MinioConfig.MINIO_ENDPOINT}/{MinioConfig.MINIO_BUCKET_NAME}/{upload_dir}/{md_summary.get('image_name')}"
            image_with_summary_and_url_list.append(
                {
                    **md_summary,
                    "url":url
                }
            )

        for image_with_summary_and_url in image_with_summary_and_url_list:
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_with_summary_and_url.get("image_name")) + r"\)")
            md_content = pattern.sub(
                f"![{image_with_summary_and_url.get('summary')}]({image_with_summary_and_url.get('url')})",
                md_content
            )
        new_md_path = md_path_obj.parent / (md_path_obj.stem+"_backup.md")
        with open(new_md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        return {
            "md_content":md_content
        }







if __name__ == '__main__':
    node = NodeMDImg()
    init_state = {
        "md_path": r"C:\Users\Administrator\Desktop\gitee\my_project\hak180产品安全手册\hak180产品安全手册.md"
    }
    res =node(init_state)
    logger.info(res)
