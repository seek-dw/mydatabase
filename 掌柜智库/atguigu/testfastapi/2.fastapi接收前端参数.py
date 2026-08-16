import shutil
import uuid
from typing import Annotated

import uvicorn
from fastapi import FastAPI, UploadFile
from fastapi.params import Path, Query, Body, Depends, File
from pydantic import BaseModel, Field
from starlette.requests import Request

app = FastAPI()




# 1.接收路径参数,路径参数是url的一部分,只要传递了就必须占位
    # testpath固定路径部分 {xxx}路径参数
    # 路由路径里面声明了一个路径参数,那么url中必须有对应的占位位置,并且实际请求也必须提供这个值
@app.get("/testpath/id/{name}/{age}")
def hello(
        # Annotated[]官方推荐写法,带注释的,Path对象被当作是int的附加额外信息
        # 否则加上#type:ignore不然老写法python语法解释器飘红
        # ...必传
        id:Annotated[int , Path(...,description="id")] ,#type: ignore
        name: Annotated[str,Path(...,description="name")],
        age: Annotated[int, Path(...,description="年龄",ge=0,le=120)]
):
    return {"id":id,"name":name,"age":age}


# 2.查询参数
    # 查询参数不需要传入url占位,只需要在接口函数中声明该参数即可
@app.get("/testquery")
def test_query(
        # 所有参数统一格式写成Annotated[类型, Path()],这种方式最灵活最好用
        # 默认值不能用老写法的Query(default=xxx)而是用Annotated[类型, Query()]=xxx
        id : Annotated[int ,Query(...,description="id")] ,
        name: Annotated[str,Query(...,description="name")],
        age: Annotated[int, Query(description="年龄")]=20,
        height: Annotated[float, Query( description="高度")]=160
):
    return {"message":"我返回了一杯手打柠檬水"}

# 3.请求体参数
    # 采用post请求
    # 请求体参数一般采用json 格式传递
    # 使用BaseModel来进行数据格式校验
        # 1.实例化对象
        # 2.检验传递的json和定义的类当中是否匹配
        # 3.返回实例化的对象

#结构化请求体参数
#定义一个类
    # Field和BaseModel都来自pydantic包
    # BaseModel是必须要传入的,因为Python的类型注解本身不会自动创建对象,解析json
class User(BaseModel):
    #只要不写默认值,pydantic就会自当认为参数必须由请求体提供
    user_name :Annotated[str, Field (...,description="用户名")]
    pass_word : Annotated[str,Field(...,description="密码")]


@app.post("/testbody")
def test_body(user:User):
    # 使用basemodel和结构类的目的就是如果前端传入的是结构化数据,后端则需要构建这么一个类来进行数据的解析
    # 如果前端传的只是一段字符串,那就无需创建类了,data : Annotated[str, Body()]即可
    # user:User 等价于告诉fastapi从请求中拿到body参数,然后按照User这个结构解析
    print(user,type(user))
    return {"user":user}

"""
    请求体参数流转全过程:
        1.postman构造http请求: 请求行,请求头,请求体
        2,请求到达uvicorn,unicorn监听8000端口,并接收http请求
        3.uvicorn把http请求交给fastapi
        4.fastapi开始寻找是否存在对应/testbody的接口(路由)
        5.fastapi开始分析,发现参数继承BaseModel并且是个对象,所以前往body获取参数
        6.fastapi根据content-type解析body,解析成python的格式
        7.pydantic接管检查传递的参数是否符合定义,符合通过产生User对象
        8.fastapi开始调用接口,执行函数\
        9.fastapi再把返回结果序列化成http response 默认是JsonResponse
"""

#4.接收混合参数,路径参数 / 查询参数 / 请求体参数同时传递
    #第一种接收方式
        #这种方式就是把三种参数都写在接口函数的参数列表中
        # 这种方式的好处是代码简单,缺点是如果参数很多,接口函数参数列表会很乱
@app.post("/testmixed/{id}")
def test_mixed(
        user:User,
        id : Annotated[int,Path(...,description="id")],
        name : Annotated[str,Query(...,description="name")],
        age : Annotated[int,Query(description="年龄")]=20
):
    return {"user":user,"id":id,"name":name,"age":age}

    #第二种接收方式(适用于参数特别多的情况,第一种不太适合使用)
        #1.使用BaseModel定义请求体参数,使用普通类定义路径和查询参数
        #2.使用依赖注入Depends类,使用它传递一个类或者函数,它会自动去调用这个类或者函数

class Student:
    def __init__(self,
                 #普通类当中一样可以使用Annotated[类型, Path() or Query()]来进行约束
                 id:Annotated[int, Path(..., description="id")],
                 name:Annotated[str, Query(..., description="name")],
                 age:Annotated[int, Query(..., description="age")]=19):
        self.id = id
        self.name = name
        self.age = age
@app.post("/testmixed2/{id}")
def text_mixed2(
        user:Annotated[User, Body(..., description="用户信息")],
        student:Annotated[Student, Depends(Student)]
):
    return{"id":student.id,"name":student.name,"age":student.age,"user":user}

#5.接收请求头的信息
@app.get("/testheader")
def test_header(req:Request):
    #实际接收的是一个req对象,里面包含了本次请求所包含的所有内容
    #直接声明Request即可,不需要也不能使用类似Body()等类似补充信息
    """fastapi基于starlette处理web/http请求"""
    print(req.headers)
    return{"message":"已完成请求头信息的接收和处理"}

#6.接收文件
    #UploadFile:框架准备好的一个文件对象类,告诉fastapi这是一个文件对象,File()告诉fastapi这个参数从form-data文件中获取
@app.post("/testfile")
def test_file(file:Annotated[UploadFile, File(..., description="文件")]):
    print(file.filename)
    print(file.file)
    print(file.headers)
    print(file.content_type)
    print(file.size)
    #前端传过来一个文件,首先要做的就是保存一下所以接口函数里面要写逻辑了
    #构造保存路径
    save_dir_path = "./uploads"
    #给文件赋予一个uuid唯一值,通过极大的数据量来避免随机值的重复生成,实现了值的唯一
    file_uuid = uuid.uuid4()
    file_name = str(file_uuid)[:9]+file.filename
    #文件流进行保存
    with open(f"{save_dir_path}/{file.filename}", "wb") as fs:
        #将原文件的数据拷贝导新文件当中,并设置一次处理文件的大小
        shutil.copyfileobj(file.file,fs,1024*1024)


    return{"message":"已完成文件接收和处理"}






















if __name__ == '__main__':
    uvicorn.run(
        app = app,
        host = "0.0.0.0",
        port = 8000
    )