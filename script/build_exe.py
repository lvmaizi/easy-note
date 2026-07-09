"""打包脚本：将桌面笔记助手打包成单文件 exe。

用法（在仓库根目录执行）：
    pip install pyinstaller
    python script/build_exe.py

产物：
    dist/EasyNote.exe          -- 单文件可执行程序
    build/                     -- PyInstaller 中间产物（可删）
    EasyNote.spec              -- 生成的 spec 文件（可删）

说明：
- 入口为仓库根目录的 run_gui.py（等价于 python -m src.ui.app）。
- 不打包 config.yaml：首次运行用代码内置默认值启动（见 src/config.py 的 _default_config），
  用户在设置对话框的修改持久化到用户配置目录（见 src/config.py 的 user_data_dir）。
- 图标：assets/icon.ico 设为 exe/快捷方式图标；assets 目录一并打入包内，
  运行时 app_icon() 经 _MEIPASS/assets/ 加载窗口图标（见 src/ui/app.py）。
- 使用 --windowed，运行时不弹出控制台黑窗。
"""

import sys
from pathlib import Path

import PyInstaller.__main__

# 仓库根目录（本脚本位于 <root>/script/）
ROOT = Path(__file__).resolve().parents[1]

APP_NAME = "EasyNote"
ENTRY = ROOT / "run_gui.py"
ICON = ROOT / "assets" / "icon.ico"   # exe/快捷方式图标
ASSETS = ROOT / "assets"              # 打入包内供运行时加载窗口图标


def main() -> None:
    if not ENTRY.exists():
        sys.exit(f"找不到入口文件: {ENTRY}")

    # PyInstaller 的 --add-data 在 Windows 上用 ; 分隔 源;目标
    sep = ";" if sys.platform.startswith("win") else ":"

    args = [
        str(ENTRY),
        "--name", APP_NAME,
        "--onefile",        # 打包为单个 exe
        "--windowed",       # GUI 程序，不显示控制台窗口
        "--clean",          # 构建前清理缓存
        "--noconfirm",      # 覆盖输出目录不询问
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT),
    ]

    # exe 文件与快捷方式图标
    if ICON.exists():
        args += ["--icon", str(ICON)]
    else:
        print(f"[警告] 未找到图标 {ICON}，exe 将使用 PyInstaller 默认图标。")

    # 把 assets 打入包内，运行时 app_icon() 经 _MEIPASS/assets/ 加载窗口图标
    if ASSETS.exists():
        args += ["--add-data", f"{ASSETS}{sep}assets"]

    print("PyInstaller 参数:")
    for a in args:
        print(" ", a)

    PyInstaller.__main__.run(args)

    print("\n打包完成。产物: " + str(ROOT / "dist" / f"{APP_NAME}.exe"))


if __name__ == "__main__":
    main()
