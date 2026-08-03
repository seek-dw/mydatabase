import shutil
import time
from pathlib import Path

import requests.api

from atguigu.config.config import MinerUConfig
from atguigu.import_process.base import NodeBase
from atguigu.tool.logger import logger


class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """
    name = "node_pdf_to_md"

    def process(self,state):

        pdf_path = state.get("pdf_path", "")
        if not pdf_path:
            logger.error("路径错误")
            raise Exception("该路径不存在")

        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("路径错误")
            raise Exception("路径错误,请上传正确的路径")

        local_dir = state.get("local_dir", "")
        if not local_dir:
            logger.error("输出路径不不存在")
            raise Exception("请提供输出路径")
        local_dir_obj = Path(local_dir)
        if not local_dir_obj.exists():
            logger.error("路径错误")
            raise Exception("请提供正确的本地目录")

        import requests

        token = MinerUConfig.MINERU_API_KEY
        url = "https://mineru.net/api/v4/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "files": [
                {"name": F"{pdf_path_obj.stem}.pdf", "data_id": "abcd"}
            ],
            "model_version": "vlm"
        }
        file_path = [f"{pdf_path}"]
        response = requests.post(url, headers=header, json=data,timeout=10)
        if response.status_code != 200:
            logger.error("向服务器发送请求失败")
            raise Exception("向服务器发送请求失败")
        result = response.json()
        if result["code"] != 0:
            logger.error("向服务器发送请求,数据返回失败")
            raise Exception("向服务器发送请求,数据返回失败")
        batch_id = result["data"]["batch_id"]
        urls = result["data"]["file_urls"]

        for i in range(0, len(urls)):
            with open(file_path[i], 'rb') as f:
                res_upload = requests.put(urls[i], data=f)
                if res_upload.status_code == 200:
                    print(f"{urls[i]} upload success")
                else:
                    print(f"{urls[i]} upload failed")

        import requests

        token = MinerUConfig.MINERU_API_KEY
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }


        total_time = 300
        use_time = 0
        while True:
            start_time = time.time()
            try:
                res = requests.get(url, headers=header,timeout=10)
                print(res.json())
                if res.status_code != 200:
                    logger.error("向服务器发送请求失败")
                    raise Exception("向服务器发送请求失败")
                result = res.json()
                if result['code'] != 0:
                    logger.error("向服务器发送请求,数据返回失败")
                    raise Exception("向服务器发送请求,数据返回失败")
                extract_result = result["data"]['extract_result'][0]
                if extract_result["state"] != "done":
                    logger.error("文件处理中")
                    raise Exception("文件处理中,请稍后")
                md_zip_urls = extract_result['full_zip_url']
                print(md_zip_urls)
                break
            except Exception as e:
                use_time += time.time() - start_time
                if use_time > total_time:
                    logger.error("处理超时")
                    raise Exception("处理超时")
                continue

        import requests
        zip_file_content = requests.get(md_zip_urls,timeout=10)
        if zip_file_content.status_code != 200:
            logger.error("向服务器发送请求失败")
            raise Exception("向服务器发送请求失败")
        zip_content = zip_file_content.content

        unzip_file_path_obj = local_dir_obj / f"{pdf_path_obj.stem}.zip"

        with open(unzip_file_path_obj, "wb") as f:
            f.write(zip_content)

        import zipfile
        unzip_content = zipfile.ZipFile(unzip_file_path_obj)

        unzip_path_obj = local_dir_obj / f"{pdf_path_obj.stem}"
        if unzip_path_obj.exists():
            shutil.rmtree(unzip_path_obj)

        unzip_path_obj.mkdir(parents=True, exist_ok=True)

        unzip_content.extractall(unzip_path_obj)


        origin_unzip_path_obj = unzip_path_obj / "full.md"
        new_unzip_path_obj = origin_unzip_path_obj.with_name(f"{pdf_path_obj.stem}.md")
        origin_unzip_path_obj.rename(new_unzip_path_obj)
        logger.info(f"解析完成,{pdf_path_obj.stem}已经保存在{new_unzip_path_obj}目录当中")

        with open(new_unzip_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        return{
            "md_content": md_content,
            "md_file_path": str(new_unzip_path_obj)
        }
















if __name__ == '__main__':
    node = NodePDFToMD()
    init_state = {
        "pdf_path": r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册.pdf",
        "local_dir" : r"C:\Users\Administrator\Desktop\gitee\my_project"
    }
    res = node(init_state)
    logger.info(res)
