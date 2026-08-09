import shutil
import time
from pathlib import Path

from fastapi import requests

from atguigu.config.config import MinerUConfig
from atguigu.import_process.base import NodeBase
from atguigu.import_process.state import ImportGraphState
from atguigu.tool.logger import logger


class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """
    name = "node_pdf_to_md"

    def process(self,state:ImportGraphState):
        pdf_path = state.get("pdf_path","")
        if not pdf_path:
            logger.error("请提供pdf文件")
            raise Exception("文件异常")
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("pdf文件目录不存在")
            raise Exception("文件目录异常")

        if not pdf_path_obj.suffix != "pdf":
            logger.error("请提供pdf文件")
            raise Exception("请提供正pdf文件")

        with open(pdf_path_obj,"rb") as f:
            pdf_content = f.read()
            if not pdf_content:
                logger.error("文件无内容")
                raise Exception("文件无内容")

        import requests

        token = MinerUConfig.MINERU_API_KEY
        url = "https://mineru.net/api/v4/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "files": [
                {"name": f"{pdf_path_obj.stem}.pdf", "data_id": "abcd"}
            ],
            "model_version": "vlm"
        }
        file_path = [f"{pdf_path}"]

        response = requests.post(url, headers=header, json=data)
        if response.status_code == 200:
            result = response.json()
            if result["code"] == 0:
                batch_id = result["data"]["batch_id"]
                urls = result["data"]["file_urls"]
                for i in range(0, len(urls)):
                    with open(file_path[i], 'rb') as f:
                        res_upload = requests.put(urls[i], data=f)
                        if res_upload.status_code == 200:
                            print(f"{urls[i]} upload success")
                        else:
                            print(f"{urls[i]} upload failed")


        token = MinerUConfig.MINERU_API_KEY
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        total_time = 30
        use_time = 0
        while True:
            start_time = time.time()
            try:
                res = requests.get(url, headers=header)
                if res.status_code !=200:
                    logger.error("向服务器发送请求失败")
                    raise Exception("向服务器发送请求失败")
                result = res.json()
                if result.get("code") != 0:
                    logger.error("向服务器发送请求,数据返回失败")
                    raise Exception("向服务器发送请求,数据返回失败")

                extract_result = result.get("data").get("extract_result")[0]
                if extract_result.get("state") != "done":
                    logger.error("文件处理中")
                    raise Exception("文件处理中,请稍后")
                md_zip_url = extract_result.get("full_zip_url")
                break
            except Exception as e:
                use_time += time.time() - start_time
                if use_time > total_time:
                    logger.error("处理超时")
                    raise Exception("处理超时")
                logger.error(e)
                continue


        md_zip = requests.get(md_zip_url)
        if md_zip.status_code != 200:
            logger.error("向服务器发送请求失败")
            raise Exception("向服务器发送请求失败")
        md_zip_content = md_zip.content
        zip_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}.zip"

        with open(zip_path, "wb") as f:
            f.write(md_zip_content)


        import zipfile

        unzip_object = zipfile.ZipFile(zip_path)
        # print(unzip_object)
        unzip_path = pdf_path_obj.parent / f"{pdf_path_obj.stem}"
        if unzip_path.exists():
            shutil.rmtree(unzip_path)

        unzip_object.extractall(unzip_path)

        origin_md = unzip_path / "full.md"
        new_md = origin_md.with_name(f"{pdf_path_obj.stem}.md")
        origin_md.rename(new_md)



if __name__ == '__main__':
    node = NodePDFToMD()
    init_state = {
        "pdf_path":r"E:\AI大模型\第七阶段 掌柜智库\资料\05-设备手册汇总\doc\hak180产品安全手册.pdf"
    }
    res = node(init_state)
    logger.info(res)