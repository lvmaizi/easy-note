"""打包脚本：将桌面笔记助手打包成 macOS 应用（.app）。

须在 **macOS 上运行**（PyInstaller 不支持跨平台交叉编译）。

用法（在仓库根目录执行）：
    pip install pyinstaller
    python3 script/build_app.py

产物：
    dist/EasyNote.app          -- 可双击运行的 macOS 应用包
    dist/EasyNote.dmg          -- 分发用 dmg 包（推荐上传到 Release）
    build/                     -- PyInstaller 中间产物（可删）
    EasyNote.spec              -- 生成的 spec 文件（可删）

说明：
- 入口为仓库根目录的 run_gui.py（等价于 python -m src.ui.app）。
- 不打包 config.yaml：首次运行用代码内置默认值启动（见 src/config.py 的 _default_config），
  用户在设置对话框的修改持久化到用户配置目录（见 src/config.py 的 user_data_dir）。
- 图标：优先用 assets/icon.icns；若仅有 icon.png，会用 sips+iconutil 现场生成 .icns
  到 build/。assets 目录一并打入包内供运行时加载窗口图标。
- 使用 --windowed，生成标准 .app 包（不带终端窗口）。
- 打包完成后自动生成 dmg 分发包；app 未签名，对方首次打开需执行
  `xattr -cr /path/to/EasyNote.app`（见 README）。
"""

import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

# 仓库根目录（本脚本位于 <root>/script/）
ROOT = Path(__file__).resolve().parents[1]

APP_NAME = "EasyNote"
BUNDLE_ID = "com.easynote.app"
ENTRY = ROOT / "run_gui.py"
ICON_ICNS = ROOT / "assets" / "icon.icns"   # macOS .app 图标（首选）
ICON_PNG = ROOT / "assets" / "icon.png"     # 退而求其次：现场生成 .icns
ASSETS = ROOT / "assets"


def _ensure_icns() -> Path | None:
    """返回可用的 .icns 路径：已有则直接用；否则用 sips+iconutil 从 png 生成到 build/。"""
    if ICON_ICNS.exists():
        return ICON_ICNS
    if not ICON_PNG.exists():
        return None

    target = ROOT / "build" / "icon.icns"
    if target.exists():
        return target

    iconset = ROOT / "build" / "icon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for s in (16, 32, 64, 128, 256, 512, 1024):
        out = iconset / f"icon_{s}x{s}.png"
        subprocess.run(
            ["sips", "-z", str(s), str(s), str(ICON_PNG), "--out", str(out)],
            check=True, capture_output=True,
        )
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(target)],
        check=True, capture_output=True,
    )
    return target


def _create_dmg(app_path: Path, out_path: Path) -> None:
    """用 hdiutil 打 dmg。相比 zip，dmg 保留符号链接与可执行位——PyInstaller
    .app 内部有大量 symlink，直接 zip 解压后会变成重复文件并可能跑不起来。"""
    if out_path.exists():
        out_path.unlink()
    cmd = [
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(app_path),
        "-ov",
        "-format", "UDZO",
        str(out_path),
    ]
    print("[dmg] " + " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    if sys.platform != "darwin":
        sys.exit("此脚本需在 macOS 上运行（PyInstaller 无法交叉编译 .app）。")
    if not ENTRY.exists():
        sys.exit(f"找不到入口文件: {ENTRY}")

    # macOS 上 --add-data 用 : 分隔 源:目标
    sep = ":"

    args = [
        str(ENTRY),
        "--name", APP_NAME,
        "--windowed",                  # 生成 .app 包（GUI，无终端窗口）
        "--osx-bundle-identifier", BUNDLE_ID,
        "--clean",                     # 构建前清理缓存
        "--noconfirm",                 # 覆盖输出目录不询问
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT),
    ]

    # .app 图标（macOS 需 .icns）
    try:
        icns = _ensure_icns()
    except subprocess.CalledProcessError as e:
        icns = None
        print(f"[警告] 生成 .icns 失败：{e.stderr.decode('utf-8', 'ignore')}")
    if icns and Path(icns).exists():
        args += ["--icon", str(icns)]
    else:
        print("[警告] 未找到可用 .icns，.app 将使用默认图标。")

    # 把 assets 打入包内，运行时 app_icon() 经 _MEIPASS/assets/ 加载窗口图标
    if ASSETS.exists():
        args += ["--add-data", f"{ASSETS}{sep}assets"]

    print("PyInstaller 参数:")
    for a in args:
        print(" ", a)

    PyInstaller.__main__.run(args)

    app_path = ROOT / "dist" / f"{APP_NAME}.app"
    print("\n打包完成。产物: " + str(app_path))

    dmg_path = ROOT / "dist" / f"{APP_NAME}.dmg"
    try:
        _create_dmg(app_path, dmg_path)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode("utf-8", "ignore") if e.stderr else str(e)
        sys.exit(f"[警告] DMG 制作失败: {err}")
    print("DMG 制作完成: " + str(dmg_path))


if __name__ == "__main__":
    main()
