# # 原始 MD
# import re
# #原始md的content
# md_content = "一些文本![旧说明](./img.png)一些文本"
# #要查找的图片文件名
# img_filename = "img.png"
# #一旦找到旧替换成新说明和minio上的url
# summary = "新\s说明" #包含特殊字符 \s 必须使用 lambda
# new_url = "https://minio/img.png"
# #正则
# pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(img_filename) + ".*?\)")
# #匹配
# #替换全部匹配的内容
# # md_content = pattern.sub(lambda m: f"![{summary}]({new_url})", md_content)
# md_content = pattern.sub(f"![{summary}]({new_url})", md_content)
#
# print(md_content)