# -*- coding: utf-8 -*-
"""屏幕二维码识别：把整块屏幕当取景框，实时找出登录二维码。"""

__version__ = "1.1.0"

from .detector import QRDecoder

__all__ = ["QRDecoder", "__version__"]
