"""
1.创建一个minio client客户端工具
2.主要是对接官网接口进行复制修改
3.代码不是重点,主要看思路
    -----统一单例模式------
    1.创建客户端client,官方复制修改
    2.根据客户端client创建自己的桶 调用 obj.make_bucket方法
    3.然后设置权限,只读权限 (权限信息转json字符串) 调用 obj.set_bucket_policy方法

"""
import json

from minio import Minio

from atguigu.config.config import MinioConfig
from atguigu.tool.logger import logger

minio_client= None
def create_minio_client():
    try:
        global minio_client
        if not minio_client:
            minio_client = Minio(
            endpoint=MinioConfig.MINIO_ENDPOINT,
            access_key=MinioConfig.MINIO_ACCESS_KEY,
            secret_key=MinioConfig.MINIO_SECRET_KEY,
            secure=False,
        )
        #创建桶
        if not minio_client.bucket_exists(bucket_name = MinioConfig.MINIO_BUCKET_NAME):
            minio_client.make_bucket(bucket_name = MinioConfig.MINIO_BUCKET_NAME)

        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": f"arn:aws:s3:::{MinioConfig.MINIO_BUCKET_NAME}",
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{MinioConfig.MINIO_BUCKET_NAME}/*",
                },
            ],
        }
        #注意要把这个policy转成json字符串,必须要是str对象
        minio_client.set_bucket_policy(bucket_name = MinioConfig.MINIO_BUCKET_NAME,policy = json.dumps(policy))
    except Exception as e:
        logger.error("minio_client初始化异常")
        raise e
    return minio_client