from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

import os
import json

# 依次尝试的数据文件
DATA_FILES = ["data_new.json", "data.json", "data2.json"]


@register("pfcmplx", "Aris", "Phantom Forces 武器查询插件", "0.2")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.guns = []
        self.load_weapon_data()

    def load_weapon_data(self):
        """加载武器数据，依次尝试多个数据文件。"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for name in DATA_FILES:
            path = os.path.join(base_dir, name)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容字典结构（例如 {"weapons": [...]} 或 {"AK-12": {...}}）
                if isinstance(data, dict):
                    for key in ("weapons", "guns", "data"):
                        if isinstance(data.get(key), list):
                            data = data[key]
                            break
                    else:
                        data = list(data.values())
                if isinstance(data, list) and data:
                    self.guns = data
                    logger.info(
                        f"成功加载武器数据: {path}，共 {len(self.guns)} 个武器"
                    )
                    return
                logger.warning(f"数据文件 {path} 格式为空或不符合预期")
            except Exception as e:
                logger.warning(f"加载数据文件 {path} 失败: {e}")
        self.guns = []
        logger.error("所有数据文件加载失败，请检查插件目录下的 data*.json 是否存在")

    @filter.command("request")
    async def request(self, event: AstrMessageEvent, target: str = ""):
        """输入武器名称以查询数据。用法: /request 武器名"""
        # 优先使用框架注入的参数；部分旧版本框架不注入时手动解析兜底
        if not target or not target.strip():
            parts = event.message_str.split()
            if len(parts) >= 2:
                target = parts[1].strip()
        target = (target or "").strip().lower()

        if not target:
            yield event.plain_result("请提供武器名称，例如: /request ak12")
            return

        if not self.guns:
            yield event.plain_result("武器数据库加载失败，请检查插件数据文件")
            return

        for gun in self.guns:
            if not isinstance(gun, dict):
                continue
            gun_name = str(gun.get("name", "") or "").strip()
            if gun_name.lower() == target:
                overview = str(gun.get("overview", "") or "")
                dsrp = str(gun.get("in_game_description", "") or "")

                result = f"武器: {gun_name}\n\n"
                if dsrp:
                    result += f"描述: {dsrp}\n\n"
                if overview:
                    result += f"数据:\n{overview}"
                else:
                    result += "该武器暂无详细数据"

                yield event.plain_result(result)
                return

        yield event.plain_result(f"未找到武器 {target}，请确认名称是否正确。")
