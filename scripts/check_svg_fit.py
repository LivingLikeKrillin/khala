"""인라인 SVG 그림의 텍스트가 자기 자리에 들어가는가 — 렌더 없이 **재서** 판정한다.

**왜 있나.** 2026-08-21 에 손으로 좌표를 계산한 그림을 렌더해 보지 않고 배포했고, 라벨이
박스를 13px 삐져나갔다. 사용자가 "성의 없어 보인다" 고 말해 줘서 알았다. 이 리포가 반복해서
적어 온 실패 그대로다 — **검사가 사람이 실제로 보는 표면을 실행하지 않으면 초록은 아무 뜻이 없다.**

**왜 잴 수 있나.** 그림의 글꼴은 JetBrains Mono 이고 모노스페이스다 — advance 가 정확히
0.6em(폰트 파일에서 실측). 그래서 텍스트 폭이 결정론이고, 브라우저 없이 판정된다. 한글은 이
폰트에 없어 시스템 폴백으로 가고 거기서 전각이므로 1.0em 으로 **보수적으로** 센다.

잡는 것 넷:
  · OVERFLOW        — 박스 안 텍스트가 박스를 넘는다
  · VIEWBOX         — 텍스트가 그림 밖으로 나간다
  · LINE-THRU-TEXT  — 연결선이 라벨을 관통한다 (렌더해 보고서야 보인 것)
  · PARSE           — SVG 가 깨졌다

검사: python scripts/check_svg_fit.py <파일...>
      인자가 없으면 docs/ 아래 전부.
"""

import re, sys, glob
from xml.etree import ElementTree

MONO = 0.6           # JetBrains Mono advance (실측)
HANGUL = 1.0         # 폴백 전각 (보수적)
SIZE = {  # class → font-size (theme.css 실측)
    "kh-fig-q": 11, "kh-fig-h": 10, "kh-fig-d": 10.5, "kh-fig-s": 9.5,
    "kh-fig-rk": 10.5, "kh-fig-ans": 12.5,
    "kh-dia-t": 11, "kh-dia-t-acc": 11, "kh-dia-s": 8.5,
    "kh-dia-lbl": 8.5, "kh-dia-glbl": 8.5,
}
TRACK = {"kh-fig-h": 0.1, "kh-dia-lbl": 0.1, "kh-dia-glbl": 0.12}  # letter-spacing em


def width(s, cls):
    fs = SIZE.get(cls)
    if fs is None:
        return None
    w = 0.0
    for ch in s:
        w += fs * (HANGUL if "\uac00" <= ch <= "\ud7a3" or "\u3130" <= ch <= "\u318f" else MONO)
    w += fs * TRACK.get(cls, 0) * max(0, len(s) - 1)
    return w



def _segments(dattr):
    """path 의 M/L 직선 구간만. 이 리포의 figure 는 곡선을 안 쓴다."""
    pts = re.findall(r'([ML])\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', dattr)
    segs, prev = [], None
    for cmd, x, y in pts:
        cur = (float(x), float(y))
        if cmd == "L" and prev:
            segs.append((prev, cur))
        prev = cur
    return segs


def _crosses(seg, box):
    """수평/수직 선분이 사각형을 지나는가. 이 리포의 연결선은 축에 평행하다."""
    (x0, y0), (x1, y1) = seg
    bx0, bx1, by0, by1 = box
    lo_x, hi_x = min(x0, x1), max(x0, x1)
    lo_y, hi_y = min(y0, y1), max(y0, y1)
    return lo_x < bx1 and bx0 < hi_x and lo_y < by1 and by0 < hi_y

def audit(path):
    src = open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r'<svg[^>]*class="(kh-fig|kh-dia)"[^>]*>.*?</svg>', src, re.S):
        svg = m.group(0)
        try:
            root = ElementTree.fromstring(svg)
        except ElementTree.ParseError as e:
            out.append((path, "PARSE", str(e), 0, 0)); continue
        vb = [float(x) for x in root.get("viewBox").split()]
        rects = []
        for r in root.findall("rect"):
            rects.append((float(r.get("x")), float(r.get("y")),
                          float(r.get("width")), float(r.get("height"))))
        for t in root.findall("text"):
            s = (t.text or "").strip()
            cls = t.get("class", "")
            w = width(s, cls)
            if not s or w is None:
                continue
            x, y = float(t.get("x")), float(t.get("y"))
            anchor = t.get("text-anchor", "start")
            x0 = x - w/2 if anchor == "middle" else (x - w if anchor == "end" else x)
            x1 = x0 + w
            # viewBox 밖으로 나가나
            if x0 < vb[0] - 0.5 or x1 > vb[0] + vb[2] + 0.5:
                out.append((path, "VIEWBOX", s, round(x0,1), round(x1,1)))
                continue
            # 이 텍스트를 세로로 품는 박스가 있으면 그 폭에 들어가야 한다
            fs = SIZE[cls]
            tbox = (x0, x1, y - fs*0.62, y + fs*0.62)
            for pth in root.findall("path"):
                for seg in _segments(pth.get("d", "")):
                    if _crosses(seg, tbox):
                        out.append((path, "LINE-THRU-TEXT", s,
                                    f"seg {seg[0]}-{seg[1]}", ""))
                        break
                else:
                    continue
                break
            for (rx, ry, rw, rh) in rects:
                if ry <= y <= ry + rh and rx <= x <= rx + rw:
                    if x0 < rx + 1 or x1 > rx + rw - 1:
                        out.append((path, "OVERFLOW", s,
                                    f"text {round(x0,1)}..{round(x1,1)}",
                                    f"box {rx}..{rx+rw}"))
                    break
    return out


import glob as _glob
files = sys.argv[1:] or sorted(
    _glob.glob("docs/src/content/docs/**/*.md", recursive=True)
    + _glob.glob("docs/src/content/docs/**/*.mdx", recursive=True))
bad = []
for f in files:
    bad += audit(f)
for b in bad:
    print("  ".join(str(x) for x in b))
print(f"\n검사한 파일 {len(files)}개 · 문제 {len(bad)}건")

# **찾기만 하고 실패하지 않으면 그물이 아니다.** 이 리포가 네 번 기록한 실패 모양이라
# 여기서 반복하지 않는다: 감지기는 종료코드로 말해야 CI 가 듣는다.
sys.exit(1 if bad else 0)
