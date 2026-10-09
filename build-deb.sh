#!/usr/bin/env bash
# 构建 emailnews 的 Ubuntu .deb 安装包
#
# 用法：
#   ./build-deb.sh              构建 deb
#   ./build-deb.sh clean        清理构建产物
#
# 依赖：dpkg-deb、gzip、python3（用于读取版本号），无第三方 Python 包。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PKG=emailnews
PY="${PYTHON:-python3}"

if [[ "${1:-}" == "clean" ]]; then
  make -C packaging clean
  rm -rf dist
  echo "已清理"
  exit 0
fi

# /tmp 在部分环境下是小容量 tmpfs，把临时目录指到项目内更稳妥
export TMPDIR="${TMPDIR:-$HERE/.tmp}"
mkdir -p "$TMPDIR"

# 版本号单一来源：emailnews/__init__.py
VERSION=$("$PY" -c "import re;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('$HERE/$PKG/__init__.py').read()).group(1))")
echo "==> 版本：$VERSION"

# 打包前先做一次导入自检，避免把坏代码打进包
echo "==> 自检：导入所有模块"
"$PY" - <<PYEOF
import sys
sys.path.insert(0, "$HERE")
import importlib
for mod in ("emailnews", "emailnews.cli", "emailnews.config", "emailnews.mailer",
            "emailnews.template", "emailnews.ui", "emailnews.services",
            "emailnews.sources", "emailnews.sources.hot", "emailnews.sources.rss",
            "emailnews.sources.net", "emailnews.sources.util", "emailnews.sources.feeds"):
    importlib.import_module(mod)
from emailnews import sources
print(f"   模块全部可导入；数据源 {len(sources.SOURCES)} 个")
PYEOF

echo "==> 组装目录树并打包"
make -C packaging >/dev/null

DEB="dist/${PKG}_${VERSION}_all.deb"
echo
echo "==> 产物：$HERE/$DEB"
ls -la "$DEB"
