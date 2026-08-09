import base64
import os
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model
from minio.deleteobjects import DeleteObject

from atguigu.config.config import MinioConfig, ModelConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.convert_to_json import convert_to_json
from atguigu.tool.logger import logger
from atguigu.tool.minio_client_tool import create_minio_client


class NodeMDImg(NodeBase):

    name = "node_md_img"


    def limit_frequency(self,total_time,current_time,dq):
        while dq and current_time - dq[0] > total_time:
            dq.popleft()
        if len(dq) == dq.maxlen:
            need_time = total_time -(current_time - dq[0])
            if need_time > 0:
                time.sleep(need_time)
                current_time = time.time()
                while dq and current_time - dq[0] > total_time:
                    dq.popleft()
        dq.append(current_time)

    def process(self, state: ImportGraphState):
        md_path = state.get("md_path", "")
        if not md_path:
            logger.info("路径不存在")
            raise Exception("路径不存在")

        md_path_obj = Path(md_path)
        if not md_path_obj:
            logger.info("路径错误")
            raise Exception("路径错误")

        with open(md_path_obj,"r", encoding="utf-8") as f:
            md_content = f.read()
            if not md_content:
                logger.info("文件内容为空")
                return {"md_content":md_content}

        image_path = md_path_obj.parent/"images"
        if not image_path.exists():
            logger.error("图片目录不存在")
            return {"md_content":md_content}

        image_name_list = os.listdir(image_path)
        image_with_context_base64_list = []
        for image_name in image_name_list:
            if Path(image_name).suffix.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]:
                logger.error(f"{image_name}、{Path(image_name).suffix}不支持的文件格式")
                continue

            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r"\)")
            match = pattern.search(md_content)
            if not match:
                logger.error(f"{image_name}不匹配正则,未被引用")
                continue
            s,e = match.span()
            pre_text = md_content[max(0,(s - 100)):s]
            next_text = md_content[e:min(len(md_content),e + 100)]

            image_name_path = image_path/image_name
            with open(image_name_path,"rb") as f:
                image_data = f.read()

            base64_image = base64.b64encode(image_data).decode("utf-8")
            image_with_context_base64_list.append(
                {
                    "image_name": image_name,
                    "base64_image": base64_image,
                    "pre_text": pre_text,
                    "next_text": next_text,
                    "md_content": md_content,
                    "image_path":image_name_path
                }
            )
        llm = init_chat_model(
            model=ModelConfig.qwen3vl_model_name,
            model_provider="openai",
            api_key= ModelConfig.qwen3vl_api_key,
            base_url=ModelConfig.qwen3vl_base_url,
            temperature=0.1
        )
        image_with_summary_list=[]
        for image_with_context_base64 in image_with_context_base64_list:
            self.limit_frequency(total_time=60,current_time=time.time(),dq=deque(maxlen=29))
            res = llm.invoke(input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式就是base64在使用的时候的规定
                                "url": "data:image/jpeg;base64," + image_with_context_base64.get("base64_image"),
                            },
                        },
                        {"type": "text", "text": f"""
                                                                               这是一张图片，图片上文部分为"{image_with_context_base64.get("pre_text")}"，
                                                                               下文部分为"{image_with_context_base64.get("next_text")}"，
                                                                               请用中文简要总结这张图片的摘要,字数在50字以内。"""
                         },
                    ],
                },])
            image_with_summary_list.append({
                **image_with_context_base64,
                "summary":res.content
            })

        upload_dir = "images_upload"
        minio_client = create_minio_client()

        list_objects = minio_client.list_objects(MinioConfig.MINIO_BUCKET_NAME, prefix=upload_dir, recursive=True)

        errors = minio_client.remove_objects(MinioConfig.MINIO_BUCKET_NAME,delete_object_list=[DeleteObject(obj.object_name) for obj in list_objects ])
        for error in errors:
            logger.error(error)


        summary_url_list = []
        for image_with_summary in image_with_summary_list:

            minio_client.fput_object(
                bucket_name=MinioConfig.MINIO_BUCKET_NAME,
                object_name=upload_dir + "/" + f"{image_with_summary.get("image_name")}",
                file_path=image_with_summary.get("image_path")
            )

            url = f"http://{MinioConfig.MINIO_ENDPOINT}/{MinioConfig.MINIO_BUCKET_NAME}/{upload_dir}/{image_with_summary.get('image_name')}"

            summary_url_list.append(
                {
                    "image_name": image_with_summary.get("image_name"),
                    "summary": image_with_summary.get("summary"),
                    "url": url
                }
            )

        for summary_url in summary_url_list:
            pattern = re.compile(r"!\[.*?\]\(.*?"+re.escape(summary_url.get("image_name"))+r"\)")
            md_content = re.sub(pattern, f"![{summary_url.get('summary')}]({summary_url.get('url')})", md_content)

        new_md_path_obj = md_path_obj.parent/ f"{md_path_obj.stem}+_new.md"

        with open(new_md_path_obj,"w", encoding="utf-8") as f:
                f.write(md_content)

        return {"md_content":md_content}


























if __name__ == '__main__':
    node = NodeMDImg()
    init_state = {
        "md_path": r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册\hak180产品安全手册.md"
    }
    res = node(init_state)
    logger.info(res)