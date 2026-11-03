# -*- coding: utf-8 -*-
"""命令行入口。

两种用法：
  screen-qr                打开实时窗口（默认）
  screen-qr --image a.png  只识别一张图片，打印结果后退出

--image 模式的意义：让识别逻辑可以在没有图形界面的环境里被验证和测试，
也方便把它当普通工具用在脚本里。
"""

from __future__ import annotations

import argparse
import sys

import cv2
import numpy as np

from . import __version__
from .detector import QRDecoder


def _imread_unicode(path: str):
    """读图。cv2.imread 在 Windows 上无法处理中文路径，这里绕开它。"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError as error:
        print(f"读不到文件：{error}", file=sys.stderr)
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def scan_image(path: str) -> int:
    image = _imread_unicode(path)
    if image is None:
        print(f"不是可识别的图片：{path}", file=sys.stderr)
        return 2

    text, points = QRDecoder().decode(image)
    if text is None:
        print("没有识别到二维码", file=sys.stderr)
        return 1

    print(text)
    if points is not None:
        xs = [float(p[0]) for p in points[0]]  # type: ignore[index]
        ys = [float(p[1]) for p in points[0]]  # type: ignore[index]
        print(
            f"位置：x {min(xs):.0f}–{max(xs):.0f}，y {min(ys):.0f}–{max(ys):.0f}",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="screen-qr",
        description="屏幕二维码识别：实时扫描屏幕，或用 --image 识别单张图片。",
    )
    parser.add_argument("--image", metavar="PATH", help="识别这张图片后退出，不打开窗口")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.image:
        return scan_image(args.image)

    try:
        from .app import main as run_gui
    except ImportError as error:  # 缺 tkinter 或图形环境
        print(f"打不开窗口：{error}", file=sys.stderr)
        print("可以改用 --image 识别单张图片。", file=sys.stderr)
        return 2

    run_gui()
    return 0
