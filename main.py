from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import os
import json

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 加载武器数据
        self.load_weapon_data()
    
    def load_weapon_data(self):
        """加载武器数据"""
        DATA_PATH_NEW = os.path.join(os.path.dirname(__file__), "data_new.json")
        DATA_PATH_OLD = os.path.join(os.path.dirname(__file__), "data.json")
        
        # 优先读取新数据库
        load_path = DATA_PATH_NEW if os.path.exists(DATA_PATH_NEW) else DATA_PATH_OLD
        
        try:
            with open(load_path, "r", encoding="utf-8") as f:
                self.guns = json.load(f)
            logger.info(f"成功加载武器数据: {load_path}，共 {len(self.guns)} 个武器")
        except Exception as e:
            logger.warning(f"加载数据库失败：{load_path}，错误：{e}")
            try:
                with open(DATA_PATH_OLD, "r", encoding="utf-8") as f:
                    self.guns = json.load(f)
                logger.info(f"成功从备用文件加载: {DATA_PATH_OLD}")
            except Exception as e2:
                logger.error(f"所有数据文件加载失败: {e2}")
                self.guns = []
    
    # 注册 request 指令
    @filter.command("request")
    async def request(self, event: AstrMessageEvent):
        """输入武器名称以查询数据。"""
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()  # 获取消息的纯文本内容
        
        logger.info(f"用户 {user_name} 触发 request 指令: {message_str}")
        
        # 检查数据是否加载成功
        if not self.guns:
            yield event.plain_result("武器数据库加载失败，请联系管理员")
            return
        
        # 提取武器名称（命令后的参数）
        parts = message_str.split()
        if len(parts) < 2:
            yield event.plain_result("请提供武器名称，例如: /request ak12")
            return
        
        target = parts[1].strip()
        logger.info(f"查询武器: {target}")
        
        # 查找武器（支持大小写不敏感）
        found = False
        for gun in self.guns:
            gun_name = gun.get("name", "")
            if gun_name.lower() == target.lower():
                found = True
                overview = gun.get("overview", "")
                dsrp = gun.get("in_game_description", "")
                
                # 构建回复消息
                result = f"武器: {gun_name}\n\n"
                if dsrp:
                    result += f"描述: {dsrp}\n\n"
                if overview:
                    result += f"数据:\n{overview}"
                else:
                    result += "该武器暂无详细数据"
                
                yield event.plain_result(result)
                logger.info(f"找到武器: {gun_name}")
                break
        
        if not found:
            yield event.plain_result(f"未找到武器 {target}，请确认名称是否正确。")
