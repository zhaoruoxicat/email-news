"""允许 `python3 -m emailnews <子命令>` 的入口。"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
