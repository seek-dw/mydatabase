import json

from bson import ObjectId


class JsonConverter(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)


def convert_to_json(data):
    #ensure_ascii=False,不会将中文转化unicode码点，而是直接输出中文
    #默认是true原因:
            # 1.兼容老协议
            # 2.数据安全
    res =json.dumps(data,ensure_ascii=False,indent=4,cls=JsonConverter)
    return res




if __name__ == '__main__':
    data = {
        "name": "张三",
        "age": 18,
        "hobbies": ["reading", "swimming"]
    }
    res = convert_to_json(data)
    print(res)