"""
定义FastAPI实例
"""
from fastapi import FastAPI

from atguigu.api.chat_router import router
from atguigu.infrastructure.db_client import init_db_engine, init_db_schema, dispose_engine
from atguigu.infrastructure.http_client import init_http_client, disposed_http_client
from atguigu.observability import setup_logging


async def lifespan(_: FastAPI):
    """
    fastapi生命周期的回调函数
    Returns:

    """

    # 1. 初始化各种资源
    print("应用启动的时候，来执行到回调函数")
    setup_logging()
    init_db_engine()
    await init_db_schema()
    init_http_client()

    # 2. 真正执行路由请求（/api/）
    yield

    # 3. 释放各种资源
    print("应用关闭的时候，来执行到回调函数")
    await dispose_engine()
    await disposed_http_client()


app = FastAPI(description="智能客服项目的FASTAPI实例", lifespan=lifespan)

# 注册路由
app.include_router(router)
