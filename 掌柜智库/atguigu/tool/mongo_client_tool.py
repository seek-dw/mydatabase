import time

from pymongo import MongoClient

from atguigu.config.config import MongoConfig



mongo_client = None
def mongo_client_create():
    global mongo_client
    if not mongo_client:
        mongo_client = MongoClient(MongoConfig.mongo_url)
    return mongo_client

collection = None
db = None

#定义获取mongo集合的函数,传入的参数就是集合的名字,默认值为"chat_history"
def get_mongo_collection(collection_name="chat_history"):
    global db
    global collection

    mongo_client = mongo_client_create()
    if db is None:
        #创建数据库
        db = mongo_client[MongoConfig.mongo_db_name]
    if collection is None:
        #创建表
        collection = db[collection_name]
        #给表创建索引
        #创建联合索引:代表_id 升序,ts降序,session_id升序索引结构
        collection.create_index([("_id",1),("ts",-1),("session_id",1)])
    return collection

def get_recent_history_list(session_id,limit = 10):
    #获取mongo里面指定的集合,默认为"chat_history"
    collection = get_mongo_collection()
    #从该集合里面查找指定session_id的聊天记录,并按ts降序排列,取前limit条
    result = collection.find({"session_id":session_id}).sort("ts",-1).limit(limit)
    #返回的时一个Cursor对象,需要遍历才能获取具体内容
    """
    增删改查的每一步操作的返回值都是一个对象
    查询的时候返回的是游标对象Cursor,防止查询大量数据导致内存崩溃,需要遍历才能获取具体内容
    新增的时候返回的是InsertOneResult对象,里面包含了重要属性就是mongodb自动生成的_id,显示为inserted_id
    更新的时候返回的是UpdateResult对象,里面包含了matched_count,和modify_count,二者分别表示匹配到的文档数量和修改的文档数量
    删除的时候返回的是DeleteResult对象,里面包含了delete_count,表示的是删除的数量
    """
    # print(result)
    return list(result)


def add_or_update_history(session_id,role,text,rewritten_query=None,item_names=None,ts=None,_id=None):
    collection = get_mongo_collection()
    #如果_id存在,说明该次函数调用传入了_id,即更新操作
    if _id:
        data = {
            "_id":_id,
            "session_id":session_id,
            "role":role,
            "text":text,
            "rewritten_query":rewritten_query,
            "item_names":item_names,
            "ts":ts or time.time()
        }
        #update_one进行更新操作:update_one(filter,update)
        collection.update_one({"_id":_id},{"$set":data})
        return _id
    #如果_id不存在,说明该次函数调用没有传入_id,即添加操作
    else:
        data = {
            "session_id":session_id,
            "role":role,
            "text":text,
            "rewritten_query":rewritten_query,
            "item_names":item_names,
            "ts":ts or time.time()
        }
        #QUESTION 添加的时候返回对象?,更新会不会返回对象,查询和删除呢?返回什么对象?有什么用?
        result = collection.insert_one(data)
        # print(result)
        # print(dir(result))
        return result.inserted_id

#通过session_id来及逆行数据库会话历史的删除操作
def clear_history(session_id):
    collection = get_mongo_collection()
    collection.delete_many({"session_id":session_id})


#重要节点:在大模型意图识别完成后返回的主体识别和问题重写豆芽更新到原来的历史记录当中
def update_item_names_and_rewritten_query(ids,item_names=None,rewritten_query = None):
    collection = get_mongo_collection()
    data = {
        "item_names":item_names,
        "rewritten_query":rewritten_query
    }
    collection.update_many({"_id":{"$in":ids}},{"$set":data})


if __name__ == '__main__':
    add_or_update_history("test_001", "user", "咨询下烫金机。")
    # add_or_update_history("test_001", "assistant", "您好。请问是哪个型号")
    # result = add_or_update_history("test_001", "user", "hak180")
    # print(result,type(result))
    # add_or_update_history("test_001", "assistant", "具体有什么问题呢？")

    # result = get_recent_history_list("test_001")
    # print(result)

    # clear_history("test_001")
