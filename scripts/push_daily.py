#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日签云端推送：企业微信群机器人（主，原生图片可存相册）+ Server酱（兜底，文字）。

触发：GitHub Actions 每天 UTC 23:25（北京时间 07:25），或 workflow_dispatch 手动测试。
密钥全部走环境变量 / GitHub Secrets，不写入代码。
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
    # Windows 若缺 tzdata，退回固定 UTC+8（中国无夏令时，等价）
    TZ = timezone(timedelta(hours=8), "UTC+8")
WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
SERVERCHAN_API = "https://sctapi.ftqq.com/{key}.send"


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


def load_image(asset_name):
    """读取仓库内的 .b64 图片文本，还原为二进制并返回 base64 + md5。"""
    path = BASE_DIR / "assets" / asset_name
    if not path.exists():
        raise FileNotFoundError("图片资源缺失: {}".format(path))
    text = path.read_text(encoding="ascii").strip()
    raw = base64.b64decode(text)
    return base64.b64encode(raw).decode("ascii"), hashlib.md5(raw).hexdigest()


def wecom_markdown(item):
    """企业微信 markdown（不支持 ``` 代码块，用引用包裹可复制文本）。"""
    return "\n".join([
        "## 日签任务卡 · {} {} · {}".format(item["date"], item["weekday"], item["flow"]),
        "**用图**：上方图片消息，长按保存到相册",
        "",
        "**贴图标题**",
        "> {}".format(item["title"]),
        "",
        "**描述**",
        "> {}".format(item["description"]),
        "",
        "**话题**",
        "> {}".format(item["topics"]),
        "",
        "**朋友圈配文**",
        "> {}".format(item["moments"]),
        "",
        "**6 步操作**",
        "1. 订阅号助手 → 底部「贴图」",
        "2. 从相册选今天的封面图",
        "3. 粘贴标题 + 描述，末尾带上话题",
        "4. 打开「允许平台推荐」← 最关键",
        "5. 点「发表」",
        "6. 右上「…」→「分享到朋友圈」→ 粘贴配文 → 发表",
        "",
        "<font color=\"warning\">贴图不能存草稿，每天必须从贴图入口新建</font>",
    ])


def serverchan_desp(item, repo):
    lines = [
        "## 日签任务卡 · {} {} · {}".format(item["date"], item["weekday"], item["flow"]),
        "",
    ]
    img_base = os.environ.get("IMAGE_URL_BASE", "").strip()
    if img_base:
        url = "{}/{}".format(img_base.rstrip("/"), quote(item["filename"]))
        lines += ["![日签封面]({})".format(url), ""]
    else:
        lines += ["> 图片见企业微信（原生消息，可长按存相册）", ""]

    lines += [
        "**用图**（本地路径）",
        "```\nD:\\工作\\微信公众号运营\\04_视觉素材\\日签封面\\{}\n```".format(item["filename"]),
        "",
        "**贴图标题**",
        "```\n{}\n```".format(item["title"]),
        "",
        "**描述**",
        "```\n{}\n```".format(item["description"]),
        "",
        "**话题**",
        "```\n{}\n```".format(item["topics"]),
        "",
        "**朋友圈配文**",
        "```\n{}\n```".format(item["moments"]),
        "",
        "**6 步操作**",
        "1. 订阅号助手 → 底部「贴图」",
        "2. 从相册选今天的封面图",
        "3. 粘贴标题 + 描述，末尾带上话题",
        "4. 打开「允许平台推荐」← 最关键",
        "5. 点「发表」",
        "6. 右上「…」→「分享到朋友圈」→ 粘贴配文 → 发表",
        "",
        "**贴图不能存草稿、不从草稿箱发，每天必须从贴图入口新建。**",
        "",
        "<sub>repo: {}</sub>".format(repo) if repo else "",
    ]
    return "\n".join(lines)


def send_wecom(webhook, item, img_b64, img_md5):
    payload_img = {"msgtype": "image", "image": {"base64": img_b64, "md5": img_md5}}
    r = requests.post(webhook, json=payload_img, timeout=20)
    r.raise_for_status()
    result = r.json()
    if result.get("errcode") != 0:
        raise RuntimeError("图片消息失败: {}".format(result))
    log("企业微信图片已送达")

    payload_md = {"msgtype": "markdown", "markdown": {"content": wecom_markdown(item)}}
    r = requests.post(webhook, json=payload_md, timeout=20)
    r.raise_for_status()
    result = r.json()
    if result.get("errcode") != 0:
        raise RuntimeError("文字消息失败: {}".format(result))
    log("企业微信文字已送达")


def send_serverchan(key, item, repo):
    url = SERVERCHAN_API.format(key=key)
    payload = {
        "title": "日签 {} · {}".format(item["mmdd"], item["title"]),
        "desp": serverchan_desp(item, repo),
    }
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    result = r.json()
    if result.get("code") != 0:
        raise RuntimeError("Server酱返回: {}".format(result))
    log("Server酱兜底已送达")


def main():
    mmdd = os.environ.get("TARGET_DATE", "").strip() or datetime.now(TZ).strftime("%m-%d")
    content = load_content()
    item = pick_today(content, mmdd)
    if item is None:
        log("{} 无日签排期，静默退出（内容包覆盖 {}）".format(mmdd, content.get("schedule", "")))
        return

    wecom = os.environ.get("WECOM_WEBHOOK", "").strip()
    sckey = os.environ.get("SERVERCHAN_KEY", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not wecom and not sckey:
        log("未配置 WECOM_WEBHOOK / SERVERCHAN_KEY，无法推送")
        sys.exit(1)

    img_b64, img_md5 = load_image(item["asset"])
    log("命中 {} · {} · {} · {}".format(mmdd, item["weekday"], item["flow"], item["title"]))

    success = 0
    if wecom:
        try:
            send_wecom(wecom, item, img_b64, img_md5)
            success += 1
        except Exception as exc:
            log("企业微信通道失败: {}".format(exc))
    if sckey:
        try:
            send_serverchan(sckey, item, repo)
            success += 1
        except Exception as exc:
            log("Server酱通道失败: {}".format(exc))

    if success == 0:
        log("全部通道失败，任务标记失败")
        sys.exit(1)
    log("推送完成，成功通道数: {}".format(success))


if __name__ == "__main__":
    main()
