# -*- coding: utf-8 -*-
"""识别核心的单元测试：不依赖图形界面，也不需要真实屏幕。

运行：python -m unittest discover -s tests -v
"""

import pathlib
import unittest

import cv2
import numpy as np

from screen_qr.detector import QRDecoder

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "qr_hello.png"
EXPECTED = "https://github.com/NPLMSHJTR/screen-qr-scanner"


class DetectorTest(unittest.TestCase):
    def setUp(self):
        self.decoder = QRDecoder()

    def test_decodes_a_plain_qr(self):
        image = cv2.imread(str(FIXTURE))
        self.assertIsNotNone(image, "fixture 缺失或无法解码")
        text, points = self.decoder.decode(image)
        self.assertEqual(text, EXPECTED)
        self.assertIsNotNone(points)

    def test_survives_low_contrast(self):
        """把二维码压暗、降低对比度后仍应识别成功——这是登录码的常见状态。"""
        image = cv2.imread(str(FIXTURE)).astype(np.float32)
        faded = np.clip(image * 0.55 + 70, 0, 255).astype(np.uint8)
        text, _ = self.decoder.decode(faded)
        self.assertEqual(text, EXPECTED)

    def test_blank_image_returns_none(self):
        blank = np.full((480, 640, 3), 255, dtype=np.uint8)
        text, points = self.decoder.decode(blank)
        self.assertIsNone(text)
        self.assertIsNone(points)


if __name__ == "__main__":
    unittest.main()
