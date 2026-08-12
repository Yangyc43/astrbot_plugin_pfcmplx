from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain
from astrbot.core.message.message_event_result import MessageChain

import asyncio
import datetime
import os
import json
import re
import subprocess
import sys


def _find_data_files():
    """按优先级收集数据文件：最新的 data_YYYY-MM-DD.json 优先，然后是内置文件。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = []
    dated = []
    try:
        for fn in os.listdir(base_dir):
            m = re.match(r"^data_(\d{4}-\d{2}-\d{2})\.json$", fn)
            if m:
                dated.append((m.group(1), fn))
    except OSError:
        pass
    dated.sort(reverse=True)
    files += [fn for _, fn in dated]
    files += ["data_new.json", "data.json", "data2.json"]
    return files


DATA_FILES = _find_data_files()


@register("pfcmplx", "Aris", "Phantom Forces 武器查询插件", "0.2")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.guns = []
        self.refreshing = False
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

    @filter.command("refresh")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def refresh(self, event: AstrMessageEvent):
        """管理员指令：从 Phantom Forces Wiki 重新抓取全部武器数据。

        用法: /refresh
        抓取结果会保存为 data_YYYY-MM-DD.json，并立即切换使用。
        """
        if self.refreshing:
            yield event.plain_result("已有刷新任务正在进行中，请耐心等待~")
            return

        base_dir = os.path.dirname(os.path.abspath(__file__))
        scraper = os.path.join(base_dir, "legancy", "scrape_weaponry.py")
        if not os.path.exists(scraper):
            yield event.plain_result("未找到爬虫脚本 legancy/scrape_weaponry.py，请确认文件存在。")
            return

        python = self._find_python()
        if not python:
            yield event.plain_result(
                "未找到带有 requests 的 Python 解释器。"
                "请在服务器上执行 pip install requests，"
                "或设置环境变量 PF_SCRAPE_PYTHON 指定解释器路径后重试。"
            )
            return

        self.refreshing = True
        asyncio.create_task(self._run_refresh(python, scraper, event))
        yield event.plain_result(
            "开始从 Phantom Forces Wiki 刷新武器数据，预计需要 10~30 分钟，完成后我会通知你~"
        )

    def _find_python(self) -> str | None:
        """找到一个可以 import requests 的 Python 解释器。"""
        candidates: list[str] = []
        env_py = os.environ.get("PF_SCRAPE_PYTHON")
        if env_py:
            candidates.append(env_py)
        candidates.append(sys.executable)  # 当前运行 AstrBot 的解释器
        candidates.append(r"E:\miniconda\python.exe")
        candidates.append("python")
        candidates.append("python3")

        for cand in candidates:
            if not cand:
                continue
            try:
                r = subprocess.run(
                    [cand, "-c", "import requests"],
                    capture_output=True,
                    timeout=15,
                )
                if r.returncode == 0:
                    logger.info(f"使用 Python 解释器: {cand}")
                    return cand
            except Exception:
                continue
        return None

    async def _run_refresh(self, python: str, scraper: str, event: AstrMessageEvent):
        """后台执行爬虫，完成后通过 event 通知管理员。"""
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            date_str = datetime.date.today().isoformat()
            out_path = os.path.join(base_dir, f"data_{date_str}.json")

            ok, msg = await asyncio.to_thread(
                self._run_scraper, python, scraper, out_path
            )
            if not ok:
                await event.send(
                    MessageChain().message(f"刷新失败：{msg}")
                )
                return

            new_guns = self._load_file(out_path)
            if not new_guns:
                await event.send(
                    MessageChain().message(f"刷新完成但新数据为空，已保留原有数据：{msg}")
                )
                return

            self.guns = new_guns
            await event.send(
                MessageChain().message(
                    f"刷新完成：共 {len(new_guns)} 件武器，"
                    f"已切换到 {os.path.basename(out_path)}。"
                )
            )
        except Exception as e:
            logger.error(f"刷新武器数据异常: {type(e).__name__}: {e}")
            try:
                await event.send(
                    MessageChain().message(f"刷新异常：{type(e).__name__}: {e}")
                )
            except Exception:
                pass
        finally:
            self.refreshing = False

    def _run_scraper(self, python: str, scraper: str, out_path: str) -> tuple[bool, str]:
        """同步执行爬虫脚本（在后台线程中调用）。"""
        cmd = [
            python,
            scraper,
            "--out",
            out_path,
            "--only_desc_overview",
            "--sleep",
            "0.8",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3600,
            )
        except subprocess.TimeoutExpired:
            return False, "爬虫执行超时（超过 1 小时）"
        except Exception as e:
            return False, f"启动爬虫失败：{type(e).__name__}: {e}"

        tail = ""
        if proc.stdout:
            tail += proc.stdout[-800:]
        if proc.stderr:
            tail += "\n" + proc.stderr[-800:]
        tail = tail.strip()

        if proc.returncode != 0:
            return False, tail or f"爬虫退出码 {proc.returncode}"
        if not os.path.exists(out_path):
            return False, tail or "未生成输出文件"

        try:
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, f"解析输出文件失败：{type(e).__name__}: {e}"

        if not isinstance(data, list) or not data:
            return False, "生成的数据文件为空"
        return True, f"{len(data)} 件武器"

    def _load_file(self, path: str) -> list:
        """从单个 JSON 文件加载武器列表，失败返回空列表。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in ("weapons", "guns", "data"):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
                else:
                    data = list(data.values())
            if isinstance(data, list) and data:
                return data
        except Exception as e:
            logger.warning(f"加载数据文件 {path} 失败: {e}")
        return []
