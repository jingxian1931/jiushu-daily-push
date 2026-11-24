#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主文云端提醒：Server酱（主，微信服务号）+ PushPlus（可选）。

- 二四六 19:28 触发，提醒 19:34 静默发表当天主文。
- 封面走 jsDelivr CDN，内嵌正文。
- 密钥走环境变量 / GitHub Secrets，不写入代码。
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    TZ = timezone(timedelta(hours=8), "UTC+8")

SERVERCHAN_API = "https://sctapi.ftqq.com/{key}.send"
PUSHPLUS_API = "http://www.pushplus.plus/send"
DEFAULT_REPO = "jingxian1931/jiushu-daily-push"


def log(msg):
    print("[{}] {}".format(datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def load_content():
    with open(BASE_DIR / "data" / "main_article_content.json", "r", encoding="utf-8") as f:
        return json.load(f)


def pick_today(content, mmdd):
    for day in content["days"]:
        if day["mmdd"] == mmdd:
            return day
    return None


def get_image_url(item):
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO).strip() or DEFAULT_REPO
    return "https://cdn.jsdelivr.net/gh/{}@main/images/{}".format(repo, quote(item["cover"]))


def task_body(item, content):
    return [
        "## 今日主文 · 待发表",
        "",
        "**{} {} · 19:34 发表**".format(item["date"], item["weekday"]),
        "",
        "![主文封面]({})".format(get_image_url(item)),
        "",
        "草稿已在公众号草稿箱写好，无需重新编辑。你只需审核后静默发表。",
        "",
        "**今天要发的主文**",
        "```\n{}\n```".format(item["title"]),
        "",
        "**审核 5 步**",
        "1. 后台 → 内容与互动 → 草稿箱 → 打开上面这篇",
        "2. 勾「声明原创」，作者「谢经娴」，转载选「禁止转载」",
        "3. 编辑页底部「添加到合集」勾「九数档案的声音·坍缩」",
        "4. 点「发表」，弹窗把「群发通知」关成灰色 ← 静默发表，不推粉丝",
        "5. 发完手机分享到朋友圈（主文唯一主动曝光渠道）",
        "",
        "**原创只能发布前勾，发完补不了。**",
        "**合集名用「的」不用「之」，与证书原名一致。**",
    ]


def send_serverchan(key, item, content):
    payload = {
        "title": "待发表 · 主文 {} · {}".format(item["mmdd"], item["title"]),
        "desp": "\n".join(task_body(item, content)),
    }
    r = requests.post(SERVERCHAN_API.format(key=key), data=payload, timeout=30)
    r.raise_for_status()
    result = r.json()
    if result.get("code") != 0:
        raise RuntimeError("Server酱返回: {}".format(result))
    log("Server酱（微信）已送达")


def send_pushplus(token, item, content):
    payload = {
        "token": token,
        "title": "待发表 · 主文 {} · {}".format(item["mmdd"], item["title"]),
        "content": "\n".join(task_body(item, content)),
        "template": "markdown",
    }
    r = requests.post(PUSHPLUS_API, json=payload, timeout=30)
    r.raise_for_status()
    result = r.json()
    if result.get("code") != 200:
        raise RuntimeError("PushPlus返回: {}".format(result))
    log("PushPlus（微信）已送达")


def main():
    mmdd = os.environ.get("TARGET_DATE", "").strip() or datetime.now(TZ).strftime("%m-%d")
    content = load_content()
    item = pick_today(content, mmdd)
    if item is None:
        log("{} 无主文排期，静默退出".format(mmdd))
        return

    sckey = os.environ.get("SERVERCHAN_KEY", "").strip()
    pptoken = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not (sckey or pptoken):
        log("未配置 SERVERCHAN_KEY / PUSHPLUS_TOKEN，无法推送")
        sys.exit(1)

    log("命中 {} · {} · {}".format(mmdd, item["weekday"], item["title"]))
    success = 0
    if sckey:
        try:
            send_serverchan(sckey, item, content)
            success += 1
        except Exception as exc:
            log("Server酱通道失败: {}".format(exc))
    if pptoken:
        try:
            send_pushplus(pptoken, item, content)
            success += 1
        except Exception as exc:
            log("PushPlus通道失败: {}".format(exc))

    if success == 0:
        log("全部通道失败，任务标记失败")
        sys.exit(1)
    log("推送完成，成功通道数: {}".format(success))


if __name__ == "__main__":
    main()
