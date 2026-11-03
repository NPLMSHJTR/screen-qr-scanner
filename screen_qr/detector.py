# -*- coding: utf-8 -*-
"""二维码识别核心：与界面无关，可单独调用、可单测。

识别策略（针对"扫登录二维码"这类密集码）：
  1. 先用原始分辨率的彩色帧识别，不缩放；
  2. 失败则转灰度做自适应二值化再试（对不均匀光照更稳）；
  3. 再失败则用 Otsu 全局阈值；
  4. 三条都不中才返回 None。
"""

import cv2


class QRDecoder:
    def __init__(self):
        self.detector = cv2.QRCodeDetector()

    def decode(self, bgr):
        """返回 (text, box_points)。识别不到返回 (None, None)。

        用原始分辨率帧识别，并做灰度+二值化增强，提升对密集登录码的识别率。
        """
        try:
            data, points, _ = self.detector.detectAndDecode(bgr)
            if data:
                return data, points
        except Exception:
            pass
        # 增强路径：灰度 + 自适应二值化后再试
        try:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            # 自适应二值化（对不均匀光照/低对比度更鲁棒）
            thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 51, 10)
            data, points, _ = self.detector.detectAndDecode(thr)
            if data:
                return data, points
            # 再试 Otsu 全局二值化
            _, thr2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data, points, _ = self.detector.detectAndDecode(thr2)
            if data:
                return data, points
        except Exception:
            pass
        return None, None
