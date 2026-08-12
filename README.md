# astrbot_plugin_pfcmplx

> [!NOTE]
> 本项目由 AI 生成，仅供学习和个人使用，请自行评估风险。

一个用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的 **Phantom Forces（罗布乐思游戏）武器数据查询插件**。

## 插件作用

在聊天软件中向 Bot 发送指令，即可快速查询《Phantom Forces》任意武器的详细信息，例如：

- 武器名称
- 游戏内描述（in-game description）
- 武器数据概览（overview，含伤害、射速、弹匣等）

示例：

```text
/request ak12
```

Bot 会返回类似下面的内容：

```text
武器: AK-12

描述: 俄罗斯联邦武装部队制式突击步枪……

数据:
伤害: 34
射速: 750 RPM
……
```

## 功能特性

- 指令：`/request <武器名>`（也支持 @机器人 + `request <武器名>`）
- 武器名匹配不区分大小写，`AK-12` / `ak12` 均可查询
- 数据以最新日期的 **`data_YYYY-MM-DD.json`** 为主，缺失时依次回退 `data_new.json`（403 件武器）、`data.json`、`data2.json`
- 管理员指令：`/refresh`——从 Phantom Forces Wiki 重新抓取全部武器数据，保存为 `data_YYYY-MM-DD.json` 并立即切换使用（需 Python 环境安装 `requests`）
- 找不到武器时会明确提示，不会静默无响应
- 兼容新旧版 AstrBot 插件 API（带 `@register` 装饰器 + 指令参数注入）

## 安装 / 部署

1. 将整个项目文件夹复制到 AstrBot 的插件目录：

   ```text
   <AstrBot 数据目录>/data/plugins/astrbot_plugin_pfcmplx/
   ```

2. 确保以下文件**完整存在**：

   - `main.py`
   - `metadata.yaml`
   - `data_new.json`（403 件武器，或任意 `data_YYYY-MM-DD.json`）
   - `legancy/scrape_weaponry.py`（`/refresh` 使用的抓取脚本）

3. 若使用 `/refresh`，请确保运行 AstrBot 的 Python 环境已安装 `requests`；也可通过环境变量 `PF_SCRAPE_PYTHON` 指定一个装有 `requests` 的 Python 解释器路径。

4. 在 AstrBot 后台或插件管理页中重载 / 重启插件。

5. 若修改过代码，直接替换文件后重新加载即可。

## 数据文件说明

| 文件 | 内容 | 优先级 |
| --- | --- | --- |
| `data_YYYY-MM-DD.json` | `/refresh` 抓取的最新武器数据库（取日期最新者） | 1（优先） |
| `data_new.json` | 完整武器数据库（403 件） | 2（回退） |
| `data.json` | 精简示例数据（6 件） | 3（回退） |
| `data2.json` | 精简示例数据（10 件） | 4（回退） |

## 技术说明

- 插件基于 AstrBot `Star` API 开发
- 入口：`main.py`
- 使用 `@filter.command("request")` 注册查询指令，通过函数签名注入参数 `target`
- 使用 `@filter.command("refresh")` + `@filter.permission_type(filter.PermissionType.ADMIN)` 注册管理员指令，后台调用 `legancy/scrape_weaponry.py` 完成抓取
- 数据文件加载顺序：最新 `data_YYYY-MM-DD.json` → `data_new.json` → `data.json` → `data2.json`

## 声明

本项目代码由 AI 辅助生成，作者不对其正确性、安全性或稳定性作任何保证。请在使用前检查代码，并遵守相关平台与游戏的使用条款。
