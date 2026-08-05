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


    def process(self, state: ImportGraphState):
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("路径不存在")
            raise Exception("路径不存在")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("路径不存在")
            raise Exception("路径不存在")

        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()
            if not md_content:
                logger.error("文件内容为空")
                return {"md_content":md_content}

        images_path_obj = md_path_obj.parent / "images"
        if not images_path_obj.exists():
            logger.error("图片路径不存在")
            return {"md_content":md_content}

        #返回字符串列表
        image_name_list = os.listdir(images_path_obj)
        if not image_name_list:
            logger.error("图片路径下没有图片")
            return {"md_content":md_content}

        image_with_pre_next_str_list= []
        length = 100
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        for image_name in image_name_list:
            if Path(image_name).suffix.lower() not in image_extensions:
                logger.error(f"{image_name}、{Path(image_name).suffix}不支持的文件格式")
                continue

            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r"\)")
            match = pattern.search(md_content)
            if not match:
                logger.error(f"{image_name}不匹配正则,未被引用")
                continue
            s , e = match.span()
            pre_text = md_content[max(0,(s - length)):s]
            next_text = md_content[e:min(len(md_content),e + length)]
            logger.info(f"{image_name}上下文get!")

            image_name_path = images_path_obj / image_name

            with open(image_name_path,"rb") as f:
                image_content = f.read()

            image_str = base64.b64encode(image_content).decode("utf-8")

            image_with_pre_next_str_list.append(
                {
                    "pre_text": pre_text,
                    "next_text": next_text,
                    "image_str" : image_str,
                    "image_name": image_name,
                    "image_name_path":image_name_path,
                    "md_content":md_content
                }
            )


        image_with_summary_list=[]
        dq = deque(maxlen =20)
        llm = None
        for image_with_pre_next_str in image_with_pre_next_str_list:
            current_time = time.time()
            while dq and current_time - dq[0] >60:
                dq.popleft()
            if len(dq) == dq.maxlen:
                sleep_time = 60 - (current_time-dq[0])
                if sleep_time > 0 :
                    time.sleep(sleep_time)
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
                                "url": "data:image/jpeg;base64," + image_with_pre_next_str.get("image_str"),
                            },
                        },
                        {"type": "text", "text": f"""
                                                               这是一张图片，图片上文部分为"{image_with_pre_next_str.get("pre_text")}"，
                                                               下文部分为"{image_with_pre_next_str.get("next_text")}"，
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
            res = llm.invoke(input=messages)
            image_with_summary_list.append(
                    {
                        "image_name": image_with_pre_next_str.get("image_name"),
                        "summary": res.content,
                        "image_name_path": image_with_pre_next_str.get("image_name_path"),
                        "md_content": image_with_pre_next_str.get("md_content"),
                    }
                )

        upload_dir = "upload_images"
        minio_client = create_minio_client()
        #上传前幂等性删除远程的仓库,递归列出来
        old_image_list = minio_client.list_objects(bucket_name = MinioConfig.MINIO_BUCKET_NAME, prefix = upload_dir,recursive = True)
        #生成器惰性删除
        errors = minio_client.remove_objects(bucket_name = MinioConfig.MINIO_BUCKET_NAME, delete_object_list=[DeleteObject(old_image.object_name) for old_image in old_image_list])
        for error in errors:
            logger.error(error)
        image_with_summary_url_list = []
        for image_with_summary in image_with_summary_list:
            minio_client.fput_object(
                bucket_name = MinioConfig.MINIO_BUCKET_NAME,
                object_name = upload_dir + "/" + image_with_summary.get("image_name"),
                file_path = image_with_summary.get("image_name_path")
            )
            url = f"http://{MinioConfig.MINIO_ENDPOINT}/{MinioConfig.MINIO_BUCKET_NAME}/{upload_dir}/{image_with_summary.get('image_name')}"

            image_with_summary_url_list.append(
                {
                    **image_with_summary,
                    "url":url,
                    "image_name":image_with_summary.get("image_name"),
                    "md_content":image_with_summary.get("md_content")
                }
            )
        for image_with_summary_url in image_with_summary_url_list:
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_with_summary_url.get("image_name")) + r"\)")
            #此处的md_content循环,每次都会发生改变,每次都替换所以,外层接收变量名要和里面的一样
            md_content = pattern.sub(
                f"![{image_with_summary_url.get('summary')}]({image_with_summary_url.get('url')})",md_content
            )
            new_md_path = md_path_obj / md_path_obj.parent / ("_new"+md_path_obj.stem+".md")
            with open(new_md_path,"w",encoding="utf-8") as f:
                f.write(md_content)
        return {
            "md_content":md_content
        }








if __name__ == '__main__':
    node = NodeMDImg()
    init_state = {
        "md_path": r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册\hak180产品安全手册.md"
    }
    res = node(init_state)
    logger.info(res)
