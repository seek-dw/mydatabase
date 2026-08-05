import json
def convert_to_json(data):
    #ensure_ascii=False,不会将中文转化unicode码点，而是直接输出中文
    #默认是true原因:
            # 1.兼容老协议
            # 2.数据安全
    res =json.dumps(data,ensure_ascii=False,indent=4)
    return res




if __name__ == '__main__':
    data = {
        "name": "张三",
        "age": 18,
        "hobbies": ["reading", "swimming"]
    }
    res = convert_to_json(data)
    print(res)