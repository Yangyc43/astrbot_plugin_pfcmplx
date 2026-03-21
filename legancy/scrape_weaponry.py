import argparse
import html as html_lib
import json
import os
import re
import time
from typing import Dict, List, Optional

import requests


API_BASE = "https://roblox-phantom-forces.fandom.com/api.php"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


SKIP_PREFIXES = (
    "Category:",
    "Template:",
    "Help:",
    "File:",
    "Special:",
    "Module:",
    "User:",
)


def fetch_parse_text(page_title: str, timeout_s: int = 30) -> str:
    """
    使用 Fandom 的 parse API 获取可解析的 HTML（比直接抓页面更不容易 403）。
    返回值是 parse.text['*'] 里的 HTML 字符串。
    """
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "text",
        "format": "json",
        "origin": "*",
    }
    r = requests.get(API_BASE, params=params, timeout=timeout_s, headers={"User-Agent": UA})
    r.raise_for_status()
    data = r.json()
    return data["parse"]["text"]["*"]


def fetch_parse_wikitext(page_title: str, timeout_s: int = 30) -> str:
    """
    使用 parse API 获取 wikitext，便于从模板参数中计算/提取字段。
    """
    params = {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
        "format": "json",
        "origin": "*",
    }
    r = requests.get(API_BASE, params=params, timeout=timeout_s, headers={"User-Agent": UA})
    r.raise_for_status()
    data = r.json()
    return data["parse"]["wikitext"]["*"]


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^<]+?>", " ", s)
    s = html_lib.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_infobox_section_html(page_html: str, heading: str) -> Optional[str]:
    """
    从 page_html 中提取以 `<h2 ...>heading</h2>` 为起点的 section HTML，直到下一个 `<h2 ...>`。
    """
    # heading 通常是纯文本，例如 Overview/Ballistics/Ammunition
    pat = re.compile(
        rf"<h2[^>]*>\s*{re.escape(heading)}\s*</h2>(.*?)(?=<h2[^>]*>|\Z)",
        flags=re.S | re.I,
    )
    m = pat.search(page_html)
    if not m:
        return None
    return m.group(0)


def parse_data_source_kv(section_html: str) -> Dict[str, str]:
    """
    在 section_html 中抓取类似：
      data-source="Weapon Class">Assault Rifle</div>
    的键值对。
    """
    # 捕获 data-source="xxx" 与后续紧跟的 >value<
    # 注意：这里是“粗抓”，用于快速拿到 Overview/Ammo 等信息。
    pat = re.compile(
        r'data-source="([^"]+)"[^>]*>([^<]+)<',
        flags=re.I | re.S,
    )
    out: Dict[str, str] = {}
    for k, v in pat.findall(section_html):
        k2 = html_lib.unescape(k).strip()
        v2 = html_lib.unescape(v).strip()
        if not k2:
            continue
        out[k2] = v2
    return out


def extract_in_game_description(page_html: str) -> str:
    """
    在 AK-12 页面中 In-game description 是 quote 段，并在属性里以 '—In-game description' 标识。
    为了稳，直接抓包含 'In-game description' 的 div.quote-body 的文本。
    """
    # 常见结构：<div class="quote-body"...> ... </div> ... —In-game description
    # 用宽松的正则：先定位 In-game description，再向前找最近的 quote-body
    if "In-game description" not in page_html:
        return ""

    idx = page_html.lower().find("in-game description")
    prefix = page_html[max(0, idx - 5000) : idx + 2000]

    # 找 quote-body
    m = re.search(r'<div[^>]*class="quote-body"[^>]*>(.*?)</div>', prefix, flags=re.S | re.I)
    if not m:
        return ""
    return strip_tags(m.group(1))


def compute_overview_from_wikitext(wt: str) -> Optional[str]:
    """
    依据 wikitext 中 Weapon/Firearm 模板参数，计算出和你 AK-12 overview 类似的行。
    失败则返回 None。
    """
    # 下面是一些可能的参数名（按 Fandom 模板习惯写死在这里）。
    def get_param(names: List[str]) -> Optional[str]:
        for name in names:
            pat = re.compile(rf"\|\s*{re.escape(name)}\s*=\s*([^|\n]+)", flags=re.I)
            m = pat.search(wt)
            if m:
                return html_lib.unescape(m.group(1)).strip()
        return None

    weapon_class = get_param(["Weapon Class"])
    unlock_rank = get_param(["Unlock Rank", "Unlock rank"])
    max_dmg = get_param(["Maximum Damage", "Max Damage", "Maximum damage"])
    min_dmg = get_param(["Minimum Damage", "Min Damage", "Minimum damage"])
    head_mul = get_param(["Headshot Multiplier", "Headshot multiplier"])
    torso_mul = get_param(["Torso Multiplier", "Torso multiplier"])
    limb_mul = get_param(["Limb Multiplier", "Limb multiplier"])
    velocity = get_param(["Velocity"])
    max_range = get_param(["Maximum Range", "Max Range", "Maximum range"])
    min_range = get_param(["Minimum Range", "Min Range", "Minimum range"])
    capacity = get_param(["Capacity"])
    round_in_chamber = get_param(["Round In Chamber", "Round in chamber", "Round in Chamber"])
    firerates = get_param(["Firerates", "Firerate", "Fire Rate", "Fire rate", "Fire Rates"])
    firemodes = get_param(["Firemodes", "Fire modes", "Fire Modes"])

    # Fire Rate 一般不在这套计算里（你 AK-12 overview 的 fire rate 行更像是从页面 Overview 段抓取的），这里先不强求。
    # 如果要做得完全一致，需要继续扩展 Fire Rate 的抽取逻辑。

    # limb/torso multipliers 有些页面可能缺失，这里默认 1
    if limb_mul is None:
        limb_mul = "1"
    if torso_mul is None:
        torso_mul = "1"

    needed = [unlock_rank, max_dmg, min_dmg, head_mul, torso_mul, limb_mul, velocity, max_range, min_range, capacity, round_in_chamber]
    if any(v is None for v in needed):
        return None

    def to_float(s: str) -> Optional[float]:
        try:
            return float(s.replace(",", "").strip())
        except Exception:
            return None

    mx = to_float(max_dmg or "")
    mn = to_float(min_dmg or "")
    hm = to_float(head_mul or "")
    tm = to_float(torso_mul or "")
    lm = to_float(limb_mul or "")
    ric = to_float(round_in_chamber or "")

    if mx is None or mn is None or hm is None or tm is None or lm is None or ric is None:
        return None

    head1 = round(mx * hm, 1)
    head0 = round(mn * hm, 1)
    def fmt_damage(v: float) -> str:
        if abs(v - int(v)) < 1e-9:
            return str(int(v))
        # 只保留 1 位小数，符合你现有数据风格
        return f"{v:.1f}"

    # torso/limb 通常是整数，但仍做通用化
    torso1 = round(mx * tm, 1)
    torso0 = round(mn * tm, 1)
    limb1 = round(mx * lm, 1)
    limb0 = round(mn * lm, 1)

    # weapon_class 有时是数字，做一个最常用的映射
    weapon_class_map = {"1": "Assault Rifle"}
    weapon_class_text = weapon_class_map.get(str(weapon_class).strip(), str(weapon_class).strip() if weapon_class else "Assault Rifle")

    cap_i = str(capacity).strip()
    ric_i = str(int(ric)) if abs(ric - int(ric)) < 1e-9 else str(ric)
    mag = f"{cap_i}+{ric_i}"

    # Fire Rate 组织成你现有数据那样：A & S | 3x B 或 “600 RPM Auto & Semi | 1800 RPM 2× Burst”
    fire_rate_text = ""
    if firerates:
        fr = str(firerates).strip()
        fr = fr.replace("<br>", "|").replace("<br/>", "|").replace("<br />", "|")
        fr = fr.replace("{{!}}", "|")
        parts = [p.strip() for p in fr.split("|") if p.strip()]
        out_parts: List[str] = []
        for p in parts:
            # 形如: "Auto & Semi: 600 RPM"
            m = re.match(r"^(.*?)\s*:\s*([0-9][0-9,]*)\s*RPM\s*$", p, flags=re.I)
            if m:
                label = m.group(1).strip()
                rpm = m.group(2).replace(",", "").strip()
                out_parts.append(f"{rpm} RPM {label}")
            else:
                out_parts.append(p)
        fire_rate_text = " | ".join(out_parts)

    if not fire_rate_text and firemodes and firerates:
        fire_rate_text = f"{firerates.strip()} {firemodes.strip()}"
    # 例如 Firerates=850（不含 RPM）
    if fire_rate_text:
        m_digits_only = re.fullmatch(r"\s*([0-9][0-9,]*)\s*", fire_rate_text, flags=re.I)
        if m_digits_only:
            num = m_digits_only.group(1).replace(",", "")
            fire_rate_text = f"{num} RPM"
    # 标准化 firemodes 文本里的常见缩写
    if firemodes:
        firemodes_norm = firemodes.strip().replace("Auto & Semi", "A & S")
    else:
        firemodes_norm = ""
    # 例如：Firerates=900 RPM，Firemodes=3× Burst & Semi
    # 这种情况你希望输出包含 firemodes 信息
    if fire_rate_text and firemodes and re.fullmatch(r"\s*[0-9][0-9,]*\s*RPM\s*", fire_rate_text, flags=re.I):
        fire_rate_text = f"{fire_rate_text} {firemodes_norm}"
    if fire_rate_text:
        fire_rate_line = f"Fire Rate: {fire_rate_text}"
    else:
        fire_rate_line = ""

    vel_num = to_float(velocity or "")
    if vel_num is None:
        velocity_text = str(velocity).replace(",", "").strip() if velocity else ""
    else:
        # 速度在页面里通常为整数
        if abs(vel_num - int(vel_num)) < 1e-9:
            velocity_text = f"{int(vel_num):,}"
        else:
            velocity_text = str(vel_num).replace(",", "").strip()

    overview_lines = [
        f"Weapon Class: {weapon_class_text}",
        f"Rank Required: {unlock_rank}",
        f"Damage dealt on head: {fmt_damage(head1)}→{fmt_damage(head0)}; On torso: {fmt_damage(torso1)}→{fmt_damage(torso0)}; On limb: {fmt_damage(limb1)}→{fmt_damage(limb0)}",
        f"Velocity: {velocity_text} studs/sec",
        f"Range: {max_range}→{min_range}",
        f"Magazine: {mag}",
    ]
    if fire_rate_line:
        overview_lines.append(fire_rate_line)
    return "\n".join(overview_lines)


def extract_overview_from_html(page_html: str) -> str:
    """
    作为兜底：把 Overview section 内的 data-source k/v 拼成文本。
    """
    sec = extract_infobox_section_html(page_html, "Overview")
    if not sec:
        return ""
    kv = parse_data_source_kv(sec)

    # 尽量映射到你 AK-12 overview 用到的字段名（可能不完全一致，但可用）
    parts: List[str] = []
    if "Weapon Class" in kv:
        parts.append(f"Weapon Class: {kv['Weapon Class']}")
    if "Unlock Rank" in kv:
        parts.append(f"Rank Required: {kv['Unlock Rank']}")

    if "Velocity" in kv:
        parts.append(f"Velocity: {kv['Velocity']} studs/sec")
    if "Maximum Range" in kv and "Minimum Range" in kv:
        parts.append(f"Range: {kv['Maximum Range']}→{kv['Minimum Range']}")

    # 容量/备用通常分别叫 Capacity/Reserves
    if "Capacity" in kv:
        res = kv.get("Reserves", "0")
        parts.append(f"Magazine: {kv['Capacity']}+{res}")

    # 如果能抓到 Fire Rate，就补上（字段名视页面而定）
    fire_rate = kv.get("Fire Rate") or kv.get("Fire rate")
    if fire_rate:
        parts.append(f"Fire Rate: {fire_rate}")

    # Damage 行通常需要计算（用 wikitext），这里暂时不一定能拼齐
    return "\n".join(parts).strip()


def extract_ballistics(page_html: str) -> str:
    sec = extract_infobox_section_html(page_html, "Ballistics")
    if not sec:
        return ""
    return strip_tags(sec)


def extract_ammunition(page_html: str) -> str:
    sec = extract_infobox_section_html(page_html, "Ammunition")
    if not sec:
        return ""
    return strip_tags(sec)


def extract_weapon_page_titles_from_weaponry(page_html: str) -> List[str]:
    """
    从 /wiki/Weaponry 页面中抽取武器条目的 page title。
    这里用“链接标题”方式：从 href="/wiki/xxx" 提取 xxx，并排除 namespace。
    """
    # 抓取 href="/wiki/XXXX"
    hrefs = re.findall(r'href="/wiki/([^"#<]+)"', page_html)
    seen = set()
    out: List[str] = []
    for h in hrefs:
        # 过滤 namespace：包含 ':' 的通常不是具体武器正文页
        if ":" in h:
            continue
        if h.startswith(("Phantom_Forces_Wiki", "Weaponry")):
            continue
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def extract_page_title_from_input(token: str) -> str:
    """
    支持 token 是：
    - 直接的页面标题，例如 "M16A4"
    - 或编辑页 URL，例如 ".../wiki/M16A4?action=edit"

    返回用于 Fandom parse API 的 page title（例如 "M16A4" 或 "VZ.806"）。
    """
    token = token.strip()
    m = re.search(r"/wiki/([^/?#]+)", token)
    if m:
        return m.group(1)
    return token


def scrape_one_weapon(
    page_title: str,
    overview_only_html: bool = False,
    include_ballistics: bool = True,
    include_ammunition: bool = True,
) -> Dict[str, str]:
    page_html = fetch_parse_text(page_title)
    in_game = extract_in_game_description(page_html)
    overview_wt = None
    if not overview_only_html:
        try:
            wt = fetch_parse_wikitext(page_title)
            overview_wt = compute_overview_from_wikitext(wt)
        except Exception:
            overview_wt = None

    overview = overview_wt or extract_overview_from_html(page_html)
    ballistics = extract_ballistics(page_html) if include_ballistics else ""
    ammunition = extract_ammunition(page_html) if include_ammunition else ""

    out: Dict[str, str] = {
        "name": page_title.replace("_", " "),
        "in_game_description": in_game,
        "overview": overview,
    }
    if include_ballistics and ballistics:
        out["ballistics"] = ballistics
    if include_ammunition and ammunition:
        out["ammunition"] = ammunition
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data.json", help="输出 JSON 文件路径（相对当前脚本运行目录）")
    ap.add_argument("--limit", type=int, default=0, help="只抓取前 N 个武器；0 表示不限制")
    ap.add_argument("--sleep", type=float, default=1.0, help="每抓一个页面的间隔秒数")
    ap.add_argument("--start", type=int, default=0, help="从第几个开始（0-based）")
    ap.add_argument("--single", default="", help="只抓取指定武器（可填标题如 M16A4，或 URL 如 .../wiki/M16A4?action=edit；也可用逗号分隔多项）")
    ap.add_argument("--overview_only_html", action="store_true", help="仅用 HTML 的 Overview section 提取 overview（用于调试字段映射）")
    ap.add_argument("--only_desc_overview", action="store_true", help="仅输出 in_game_description + overview（不抓 ballistics/ammunition）")
    ap.add_argument("--append", action="store_true", help="把抓到的结果追加进 out 指向的现有 JSON（不覆盖旧数据）")
    ap.add_argument("--overwrite", action="store_true", help="当 --append 且名字重复时，用新抓到的数据覆盖旧数据")
    args = ap.parse_args()

    if args.single:
        raw_items = [x.strip() for x in args.single.split(",") if x.strip()]
        titles = [extract_page_title_from_input(x) for x in raw_items]
    else:
        weaponry_html = fetch_parse_text("Weaponry")
        titles = extract_weapon_page_titles_from_weaponry(weaponry_html)

    if args.limit and args.limit > 0:
        titles = titles[args.start : args.start + args.limit]
    else:
        titles = titles[args.start:]

    existing: List[Dict[str, str]] = []
    existing_index_by_name: Dict[str, int] = {}

    if args.append and os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if isinstance(existing, list):
            for i, item in enumerate(existing):
                if isinstance(item, dict) and "name" in item:
                    existing_index_by_name[str(item["name"])] = i
        else:
            existing = []
            existing_index_by_name = {}

    # 只保留你需要的两个字段，避免旧数据里带了 ballistics/ammunition
    if args.only_desc_overview:
        kept: List[Dict[str, str]] = []
        for item in existing:
            if isinstance(item, dict):
                kept.append(
                    {
                        "name": item.get("name", ""),
                        "in_game_description": item.get("in_game_description", ""),
                        "overview": item.get("overview", ""),
                    }
                )
        existing = kept
        existing_index_by_name = {}
        for i, item in enumerate(existing):
            if isinstance(item, dict) and item.get("name"):
                existing_index_by_name[str(item["name"])] = i

    results: List[Dict[str, str]] = list(existing)
    for i, t in enumerate(titles):
        print(f"[{i+1}/{len(titles)}] scraping {t} ...")
        try:
            include_ballistics = not args.only_desc_overview
            include_ammunition = not args.only_desc_overview
            item = scrape_one_weapon(
                t,
                overview_only_html=args.overview_only_html,
                include_ballistics=include_ballistics,
                include_ammunition=include_ammunition,
            )
            name = str(item.get("name", ""))
            if name and name in existing_index_by_name:
                if args.append and args.overwrite:
                    results[existing_index_by_name[name]] = item
                else:
                    print(f"  skip (already exists): {name}")
            else:
                results.append(item)
                if name:
                    existing_index_by_name[name] = len(results) - 1
        except Exception as e:
            print(f"  failed: {type(e).__name__}: {e}")
        time.sleep(args.sleep)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"done. wrote {len(results)} items to {args.out}")


if __name__ == "__main__":
    main()

