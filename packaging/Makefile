#!/usr/bin/make -f
# 极简 debian 打包规则：不依赖 debhelper，直接组装目录树后用 dpkg-deb 成品。
# 因为本包是纯 Python（无编译步骤），用 make 反而比 debhelper 更直观、可控。
#
# 约定：本 Makefile 位于 packaging/ 下，源码与 demo.html 在其上一级。

ROOT_SRC  := $(abspath $(CURDIR)/..)
PACKAGE   := emailnews
VERSION   := $(shell python3 -c "import re;print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('$(ROOT_SRC)/emailnews/__init__.py').read()).group(1))")
ARCH      := all
BUILD     := build
DEST      := $(BUILD)/$(PACKAGE)_$(VERSION)_$(ARCH)

.PHONY: all clean dirs control data

all: dirs control data
	@echo "==> 生成 $(PACKAGE)_$(VERSION)_$(ARCH).deb"
	@mkdir -p $(ROOT_SRC)/dist
	dpkg-deb --root-owner-group --build $(DEST) $(ROOT_SRC)/dist/$(PACKAGE)_$(VERSION)_$(ARCH).deb
	@echo "==> 完成：$(ROOT_SRC)/dist/$(PACKAGE)_$(VERSION)_$(ARCH).deb"

dirs:
	@rm -rf $(DEST)
	@mkdir -p $(DEST)/DEBIAN
	@mkdir -p $(DEST)/usr/bin
	@mkdir -p $(DEST)/opt/$(PACKAGE)
	@mkdir -p $(DEST)/usr/share/$(PACKAGE)

# 控制信息：版本号从 __init__.py 自动读取，避免两处手改
control:
	@sed -e "s/@VERSION@/$(VERSION)/g" debian/control.in > $(DEST)/DEBIAN/control
	@cp debian/copyright $(DEST)/DEBIAN/copyright
	@cp debian/postinst $(DEST)/DEBIAN/postinst
	@cp debian/prerm $(DEST)/DEBIAN/prerm
	@cp debian/postrm $(DEST)/DEBIAN/postrm
	@chmod 755 $(DEST)/DEBIAN/postinst $(DEST)/DEBIAN/prerm $(DEST)/DEBIAN/postrm

data:
	# Python 包本体
	@cp -r $(ROOT_SRC)/emailnews $(DEST)/opt/$(PACKAGE)/emailnews
	@find $(DEST)/opt/$(PACKAGE) -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	@find $(DEST)/opt/$(PACKAGE) -name '*.pyc' -delete 2>/dev/null || true
	# 邮件模板（demo.html）作为数据文件放进 share，便于用户自行改版式
	@cp $(ROOT_SRC)/demo.html $(DEST)/usr/share/$(PACKAGE)/demo.html
	# 启动器
	@cp debian/emailnews-launcher $(DEST)/usr/bin/$(PACKAGE)
	@chmod 755 $(DEST)/usr/bin/$(PACKAGE)
	# 手册页
	@mkdir -p $(DEST)/usr/share/man/man1
	@gzip -9c debian/emailnews.1 > $(DEST)/usr/share/man/man1/$(PACKAGE).1.gz

clean:
	rm -rf $(BUILD)
