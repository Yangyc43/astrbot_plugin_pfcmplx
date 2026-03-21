from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

@register("pfcmplx", "Aris", "武器查询插件", "0.1")
class pfcmplx(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        logger.info("✅ 武器查询插件初始化成功")
    
    @filter.command("test")
    async def test(self, event: AstrMessageEvent):
        """测试命令"""
        yield event.plain_result("插件工作正常！")
    
    @filter.command("request")
    async def request(self, event: AstrMessageEvent, weapon_name: str = None):
        """查询武器数据"""
        yield event.plain_result(f"你查询的武器是: {weapon_name}")
    
    async def terminate(self):
        logger.info("武器查询插件已卸载")