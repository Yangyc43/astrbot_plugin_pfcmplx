from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import os
import json

DATA_PATH_NEW = os.path.join(os.path.dirname(__file__), "data_new.json")
DATA_PATH_OLD = os.path.join(os.path.dirname(__file__), "data.json")

# 优先读取新数据库；避免新库出问题导致插件启动失败
load_path = DATA_PATH_NEW if os.path.exists(DATA_PATH_NEW) else DATA_PATH_OLD
try:
    with open(load_path, "r", encoding="utf-8") as f:
        guns = json.load(f)  # guns 是一个 list[dict]
except Exception as e:
    logger.warning(f"加载数据库失败：{load_path}，将回退读取：{DATA_PATH_OLD}。错误：{type(e).__name__}: {e}")
    with open(DATA_PATH_OLD, "r", encoding="utf-8") as f:
        guns = json.load(f)

@register("pfcmplx", "Aris", "pfcmplx", "0.1")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
    
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def request(self, event: AstrMessageEvent):
        """输入武器名称以查询数据。""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *

        # 新功能：遍历查找目标武器，找到则输出 overview，找不到则返回错误
        tgtweapon = message_str[9:].strip()      
        found = False
        for gun in guns:
            if gun.get("name") == tgtweapon:
                found = True
                overview = gun.get("overview", "")
                if overview:
                    yield event.plain_result(f"返回数据如下:\n {overview}")  # 保持原来的输出格式
                else:
                    yield event.plain_result(f"找到武器 `{tgtweapon}`，但该武器没有 overview 字段。")
                break
        if not found:
            yield event.plain_result(f"未找到武器 {tgtweapon}，请确认名称是否正确。")
        logger.info(message_chain)
        return
    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
