# 屏幕二维码识别（screen-qr-scanner）

电脑上弹出的登录二维码，用手机去扫自己的屏幕很别扭。这个工具把整块屏幕当成取景框：
二维码一出现在屏幕任何位置，它直接把内容抓出来，省掉"举手机对屏幕"这一步。

它把屏幕画面实时渲染在窗口里（像投屏），同时对画面持续做识别；识别到就用原始全分辨率帧再确认一次，
成功后在画面上框出二维码，并弹出可复制的文本。

```
┌──────────────────────────────────────────┐
│ 屏幕扫码   ● 识别中            [暂停] [✕] │
├──────────────────────────────────────────┤
│                                          │
│         （实时屏幕画面，等比缩放）        │
│              ┌──────┐                    │
│              │ 二维码│ ← 识别到画绿框     │
│              └──────┘                    │
├──────────────────────────────────────────┤
│ 右键拖选区域 · 空格暂停 · 双击复制 · Esc 退出 │
└──────────────────────────────────────────┘
```

## 为什么不能"缩到几十像素再识别"

登录二维码通常是比较密集的版本，模块数多、单模块像素少。
把 2560×1440 的屏幕缩到几百像素再识别，模块边界会被插值抹平，识别率会明显下降。
所以这里的分工是：**识别用原始分辨率帧，显示才缩放**。这条是踩过坑之后定下来的。

识别失败时还会依次尝试两条增强路径：灰度 + 自适应二值化（应对屏幕反光、暗色主题下对比度不足），
以及 Otsu 全局阈值（应对整屏偏暗）。三条都不中才判定"没有二维码"。

## 安装

```bash
git clone https://github.com/NPLMSHJTR/screen-qr-scanner.git
cd screen-qr-scanner
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

要求 Python 3.9+。`tkinter` 随 Windows 官方 Python 一起安装；Debian/Ubuntu 需要额外装 `python3-tk`。

## 使用

```bash
# 实时窗口（默认）
python -m screen_qr

# 只识别一张图片，打印结果后退出
python -m screen_qr --image sample.png
```

| 操作 | 作用 |
|---|---|
| 右键在画面上拖一个矩形 | 只在该区域内识别 |
| `R` | 取消选区，恢复全屏识别 |
| `空格` | 暂停 / 恢复识别（画面继续刷新） |
| 双击画面 或 `C` | 复制最近一次识别结果 |
| `Esc` 或标题栏 `✕` | 退出 |

## 作为库使用

识别核心与界面是分开的，可以只拿 `QRDecoder`：

```python
import cv2
from screen_qr.detector import QRDecoder

frame = cv2.imread("sample.png")
text, points = QRDecoder().decode(frame)
print(text, points)
```

`decode()` 接受 BGR 的 `numpy.ndarray`，返回 `(text, points)`；识别不到时返回 `(None, None)`，不抛异常。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试不打开窗口，只验证识别核心：正常二维码、压暗降对比度后的二维码、纯白空白图。

## 已知限制

- **主要面向 Windows**。DPI 感知通过 `ctypes.windll` 设置，非 Windows 上会跳过；其余部分理论上跨平台，但**没有在 macOS / Linux 上实测过**。
- **只抓主显示器**（`mss.monitors[1]`）。多屏环境下副屏上的二维码识别不到。
- 识别用的是 OpenCV 自带的 `QRCodeDetector`，对**变形、遮挡、彩色反相**的二维码容忍度有限；这是算法本身的边界，不是参数问题。
- 窗口置顶（`-topmost`）意味着它会盖住别的窗口，全屏应用下需要先切换出来。

## 隐私

整个过程在本机完成：屏幕帧不落盘、不上传，识别结果只存在内存里，退出即消失。
唯一的网络行为发生在你自己点"打开链接"时。

## 许可

MIT，见 [LICENSE](LICENSE)。
