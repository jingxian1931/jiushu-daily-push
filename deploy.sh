#!/usr/bin/env bash
# 一键部署：需先在本机终端执行 gh auth login 完成浏览器登录
set -euo pipefail

REPO_OWNER="jingxian1931"
REPO_NAME="jiushu-daily-push"
DIR="D:/工作/微信公众号运营/06_发布执行/日签云端推送"

cd "$DIR"
git init -q
git config user.name "$REPO_OWNER"
git config user.email "$REPO_OWNER@users.noreply.github.com"
git add -A
git commit -q -m "init: 日签云端推送（企业微信主 + Server酱兜底）"
git branch -M main

if gh repo view "$REPO_OWNER/$REPO_NAME" >/dev/null 2>&1; then
  echo "仓库已存在，仅推送代码"
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$REPO_OWNER/$REPO_NAME.git"
  git push -u origin main
else
  echo "创建私有仓库并推送"
  gh repo create "$REPO_NAME" \
    --private \
    --description "九数档案日签云端推送 · 企业微信主 + Server酱兜底 · 北京07:25" \
    --source=. \
    --remote=origin \
    --push
fi

echo "完成：https://github.com/$REPO_OWNER/$REPO_NAME"
