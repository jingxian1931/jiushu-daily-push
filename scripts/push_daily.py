#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日签云端推送：Server酱（主，微信服务号）+ PushPlus（可选）+ 企业微信（可选）。

- 图片走 GitHub raw 公网链接，内嵌在 Server酱/PushPlus 的 Markdown 正文里，手机长按可存。
- 任一通道配置即推送；全部失败才标记任务失败。
- 密钥全部走环境变量 / GitHub Secrets，不写入代码。
"""
import base64
import hashlib
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
    with open(BASE_DIR / "data" / "daily_content.json", "r", encoding="utf-8") as f:
        return json.load(f)


def pick_today(content, mmdd):
    for day in content["days"]:
        if day["mmdd"] == mmdd:
            return day
    return None


def get_image_url(item):
    """图片公网地址：优先自定义图床，否则用 jsDelivr CDN（国内可达性好）。"""
    base = os.environ.get("IMAGE_URL_BASE", "").strip()
    if base:
        return "{}/{}".format(base.rstrip("/"), quote(item["filename"]))
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO).strip() or DEFAULT_REPO
    return "https://cdn.jsdelivr.net/gh/{}@main/images/{}".format(repo, quote(item["filename"]))


def task_body(item):
    """各通道共用的正文（Markdown）。草稿已写好，提醒审核发表。"""
    draft = item.get("draft_title") or ("每日签 {}｜{}".format(item["mmdd"], item["title"]))
    return [
        "## 今日日签 · 待审核发表",
        "",
        "**{} {} · {}**".format(item["date"], item["weekday"], item["flow"]),
        "",
        "![日签封面]({})".format(get_image_url(item)),
        "",
        "草稿已在公众号草稿箱写好，封面 / 标题 / 作者 / 摘要 / 正文全部填好，无需再粘贴。你只需审核后发表。",
        "",
        "**草稿箱里找这一篇**",
        "```\n{}\n```".format(draft),
        "",
        "**朋友圈配文**",
        "```\n{}\n```".format(item["moments"]),
        "",
        "**审核 4 步**",
        "1. 手机订阅号助手 → 草稿箱 → 找到上面那篇",
        "2. 点开检查正文与封面（标题作者已填好，无需改动）",
        "3. 打开「允许平台推荐」← 最关键，关了几乎没自然流量",
        "4. 点「发表」→ 右上「…」→「分享到朋友圈」→ 粘贴配文 → 发表",
        "",
        "**只需审核点发表，不用重新编辑草稿。**",
    ]


def send_serverchan(key, item):
    payload = {
        "title": "待审核发表 · 日签 {} · {}".format(item["mmdd"], item["title"]),
        "desp": "\n".join(task_body(item)),
    }
    r = requests.post(SERVERCHAN_API.format(key=key), data=payload, timeout=30)
    r.raise_for_status()
    result = r.json()
    if result.get("code") != 0:
        raise RuntimeError("Server酱返回: {}".format(result))
    log("Server酱（微信）已送达")


def send_pushplus(token, item):
    payload = {
        "token": token,
        "title": "待审核发表 · 日签 {} · {}".format(item["mmdd"], item["title"]),
        "content": "\n".join(task_body(item)),
        "template": "markdown",
    }
    r = requests.post(PUSHPLUS_API, json=payload, timeout=30)
    r.raise_for_status()
    result = r.json()
    if result.get("code") != 200:
        raise RuntimeError("PushPlus返回: {}".format(result))
    log("PushPlus（微信）已送达")


def send_wecom(webhook, item):
    """企业微信为可选通道：原生图片消息（可长按存相册）+ 文字。"""
    path = BASE_DIR / "assets" / item["asset"]
    if not path.exists():
        raise FileNotFoundError("图片资源缺失: {}".format(path))
    raw = base64.b64decode(path.read_text(encoding="ascii").strip())
    payload_img = {
        "msgtype": "image",
        "image": {"base64": base64.b64encode(raw).decode("ascii"),
                  "md5": hashlib.md5(raw).hexdigest()},
    }
    r = requests.post(webhook, json=payload_img, timeout=20)
    r.raise_for_status()
    if r.json().get("errcode") != 0:
        raise RuntimeError("企微图片失败: {}".format(r.json()))
    log("企业微信图片已送达")

    text = "\n".join([
        "## 今日日签 · 待审核发表",
        "> {} {} · {}".format(item["date"], item["weekday"], item["flow"]),
        "> 草稿箱找：{}".format(item.get("draft_title", item["title"])),
        "> 配文：{}".format(item["moments"]),
        "<font color=\"warning\">草稿已写好，只需审核点发表，不用重新编辑</font>",
    ])
    r = requests.post(webhook, json={"msgtype": "markdown", "markdown": {"content": text}}, timeout=20)
    r.raise_for_status()
    if r.json().get("errcode") != 0:
        raise RuntimeError("企微文字失败: {}".format(r.json()))
    log("企业微信文字已送达")


def main():
    mmdd = os.environ.get("TARGET_DATE", "").strip() or datetime.now(TZ).strftime("%m-%d")
    content = load_content()
    item = pick_today(content, mmdd)
    if item is None:
        log("{} 无日签排期，静默退出（内容包覆盖 {}）".format(mmdd, content.get("schedule", "")))
        return

    sckey = os.environ.get("SERVERCHAN_KEY", "").strip()
    pptoken = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    wecom = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not (sckey or pptoken or wecom):
        log("未配置 SERVERCHAN_KEY / PUSHPLUS_TOKEN / WECOM_WEBHOOK，无法推送")
        sys.exit(1)

    log("命中 {} · {} · {} · {}".format(mmdd, item["weekday"], item["flow"], item["title"]))
    success = 0
    if sckey:
        try:
            send_serverchan(sckey, item)
            success += 1
        except Exception as exc:
            log("Server酱通道失败: {}".format(exc))
    if pptoken:
        try:
            send_pushplus(pptoken, item)
            success += 1
        except Exception as exc:
            log("PushPlus通道失败: {}".format(exc))
    if wecom:
        try:
            send_wecom(wecom, item)
            success += 1
        except Exception as exc:
            log("企业微信通道失败: {}".format(exc))

    if success == 0:
        log("全部通道失败，任务标记失败")
        sys.exit(1)
    log("推送完成，成功通道数: {}".format(success))


if __name__ == "__main__":
    main()
