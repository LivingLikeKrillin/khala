"""README 그림을 만든다 — 한국어와 영어, 밝은 판과 다크 판, 모두 여덟 장이고 배치는 하나다.

    python assets/diagrams/gen.py

문구는 `labels.json` 에 있다. 그림 안 문장을 고치면 그 파일을 고치고 다시 돌린다.
"""
import json
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
with open(os.path.join(HERE, "labels.json"), encoding="utf-8") as fh:
    L = json.load(fh)

SANS = ("'Helvetica Neue', Helvetica, Arial, 'Apple SD Gothic Neo', 'Malgun Gothic', "
        "'Noto Sans KR', 'Noto Sans CJK KR', sans-serif")
MONO = "Menlo, Consolas, 'DejaVu Sans Mono', monospace"
LIGHT = dict(paper="#ffffff", ink="#262626", grey="#6f6f6f", hair="#bdbdbd", gov="#2b3f6b",
             tint="#e8ebf3", gov2="#cfd6e6", cmd="#b23a1d", white="#ffffff", govtext="#2b3f6b")
DARK = dict(paper="#1a1a1a", ink="#e6e6e6", grey="#9a9a9a", hair="#4a4a4a", gov="#2b3f6b",
            tint="#232a3a", gov2="#cfd6e6", cmd="#d4654a", white="#ffffff", govtext="#cfd6e6")
P = dict(LIGHT)

MARKER = ('markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" '
          'refX="8" refY="5" orient="auto"')


def defs():
    ink, cmd = P["ink"], P["cmd"]
    return "\n".join([
        "  <defs>",
        f'    <marker id="data" {MARKER}>',
        f'      <path d="M1,1 L8,5 L1,9" fill="none" stroke="{ink}" stroke-width="1.2"/>',
        "    </marker>",
        f'    <marker id="cmd" {MARKER}>',
        f'      <path d="M0,1 L9,5 L0,9 Z" fill="{cmd}"/>',
        "    </marker>",
        "  </defs>",
    ])


def t(lang, key):
    return escape(L[key][lang])


def text(x, y, s, size=11, fill=None, weight=None, mono=False, anchor=None):
    a = [f'x="{x}"', f'y="{y}"', f'font-size="{size}"']
    if fill:
        a.append(f'fill="{fill}"')
    if weight:
        a.append(f'font-weight="{weight}"')
    if anchor:
        a.append(f'text-anchor="{anchor}"')
    if mono:
        a.append(f'font-family="{MONO}"')
    return f'    <text {" ".join(a)}>{s}</text>'


def rect(x, y, w, h, fill, stroke, rest=""):
    return (f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'fill="{fill}" stroke="{stroke}"{rest}/>')


def box(kind, x, y, w, h, name, roles):
    """kind: external | project | core. 이름 한 줄 + 역할 최대 두 줄, 왼쪽 정렬, 안쪽 여백 12."""
    out = []
    if kind == "external":
        out.append(rect(x, y, w, h, P["paper"], P["hair"]))
        out.append(text(x + 12, y + 23, name, 12, mono=True))
        role_fill = P["grey"]
    elif kind == "project":
        out.append(rect(x, y, w, h, P["tint"], P["gov"], ' stroke-width="1.5"'))
        out.append(text(x + 12, y + 23, name, 12.5, weight=700, mono=True))
        role_fill = P["grey"]
    else:
        out.append(rect(x, y, w, h, P["gov"], P["gov"], ' stroke-width="1.5"'))
        out.append(rect(x + 4, y + 4, w - 8, h - 8, "none", P["white"],
                        ' stroke-width="0.75" stroke-opacity="0.6"'))
        out.append(text(x + 12, y + 23, name, 12.5, fill=P["white"], weight=700, mono=True))
        role_fill = P["gov2"]
    for i, r in enumerate(roles):
        out.append(text(x + 12, y + 39 + 16 * i, r, 11, fill=role_fill))
    return out


def leg(x, y, name, role):
    """작은 구성요소 상자, 104 x 44."""
    return [rect(x, y, 104, 44, P["tint"], P["gov"], ' stroke-width="1.5"'),
            text(x + 12, y + 19, name, 12.5, weight=700, mono=True),
            text(x + 12, y + 35, role, 11, fill=P["grey"])]


def group(attrs):
    return f"    <g {attrs}>"


def key(items, y):
    """범례 한 줄. items: (kind, label) 목록, 왼쪽부터 글자 폭을 어림해 늘어놓는다."""
    out = [f'  <g font-size="10.5" fill="{P["grey"]}">']
    x = 20
    for kind, label in items:
        if kind in ("data", "write"):
            stroke, width = (P["ink"], "1.2") if kind == "data" else (P["cmd"], "2")
            out.append(f'    <path d="M{x},{y - 4} H{x + 24}" fill="none" stroke="{stroke}" '
                       f'stroke-width="{width}"/>')
        elif kind == "project":
            out.append(rect(x + 10, y - 10, 14, 10, P["tint"], P["gov"], ' stroke-width="1.5"'))
        elif kind == "core":
            out.append(rect(x + 10, y - 10, 14, 10, P["gov"], P["gov"]))
        elif kind == "external":
            out.append(rect(x + 10, y - 10, 14, 10, "none", P["hair"]))
        out.append(f'    <text x="{x + 30}" y="{y}">{label}</text>')
        width = sum(10.5 if "가" <= ch <= "힣" else 6.2 for ch in label)
        x += 30 + int(width) + 28
        x -= x % 4
    out.append("  </g>")
    return out


def head(w, h, lang, desc_key):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{t(lang, desc_key)}">',
            defs(),
            f'  <g font-family="{SANS}" fill="{P["ink"]}">']


def same_information(lang):
    o = head(840, 412, lang, "d1.desc")
    o.append(text(20, 36, "Khala", 17, weight=700, mono=True))
    o.append(text(20, 56, t(lang, "d1.desc"), 12, fill=P["grey"]))
    o.append(text(820, 36, t(lang, "d1.note1"), 11, fill=P["grey"], anchor="end"))
    o.append(text(820, 52, t(lang, "d1.note2"), 11, fill=P["grey"], anchor="end"))
    rows = [("Nexus", "d1.nexus.role"), ("Arbiter", "d1.arbiter.role"),
            ("Observer", "d1.observer.role"), ("Adept", "d1.adept.role")]
    for i, (name, rk) in enumerate(rows):
        o += box("project", 32, 96 + 68 * i, 220, 52, name, [t(lang, rk)])
    o += box("core", 376, 188, 160, 72, t(lang, "d1.core.name"),
             [t(lang, "d1.core.role1"), t(lang, "d1.core.role2")])
    o += box("external", 648, 140, 160, 52, t(lang, "d1.human.name"), [t(lang, "d1.human.role")])
    o += box("external", 648, 256, 160, 52, t(lang, "d1.agent.name"), [t(lang, "d1.agent.role")])
    o.append(group(f'fill="none" stroke="{P["ink"]}" stroke-width="1.2"'))
    for i in range(4):
        o.append(f'      <path d="M252,{122 + 68 * i} H284"/>')
    o += ['      <path d="M284,122 V326"/>',
          '      <path d="M284,224 H374" marker-end="url(#data)"/>',
          '      <path d="M536,224 H576 V166 H646" marker-end="url(#data)"/>',
          '      <path d="M576,224 V282 H646" marker-end="url(#data)"/>',
          "    </g>"]
    o.append(group(f'font-size="10.5" fill="{P["ink"]}"'))
    o.append(text(292, 217, t(lang, "d1.edge.feed"), 10.5))
    o.append(text(584, 159, t(lang, "d1.edge.human"), 10.5))
    o.append(text(584, 275, t(lang, "d1.edge.agent"), 10.5))
    o += ["    </g>", "  </g>"]
    o += key([("data", t(lang, "d1.key.data")), ("project", t(lang, "d1.key.project")),
              ("core", t(lang, "d1.key.core")), ("external", t(lang, "d1.key.external"))], 394)
    o.append("</svg>")
    return "\n".join(o) + "\n"


#: 답변 경로 그림의 데이터 선. 꺾임은 직각만.
ANSWER_EDGES = [
    ("M420,128 V180 H180 V194", True), ("M420,180 H456 V194", True),
    ("M180,248 V280 H104 V306", True), ("M180,280 H224 V306", True),
    ("M456,248 V280 H344 V306", True), ("M456,280 H464 V306", True),
    ("M634,330 H518", True),
    ("M104,352 V376 H464 V352", False), ("M224,352 V376", False), ("M344,352 V376", False),
    ("M316,376 V402", True), ("M316,456 V498", True), ("M720,356 V536 H518", True),
    ("M446,572 V614", True), ("M356,642 H274", True), ("M536,642 H634", True),
    ("M576,212 H824 V642 H810", True), ("M52,642 H16 V102 H318", True),
]

#: (x, y, 문구 키) — 선 라벨.
ANSWER_LABELS = [
    (428, 144, "d2.edge.ask"), (188, 272, "d2.edge.toIdentifierLegs"),
    (464, 272, "d2.edge.toOriginalLegs"), (524, 323, "d2.edge.pgToLegs"),
    (324, 396, "d2.edge.toFuse"), (324, 482, "d2.edge.toPacket"),
    (728, 452, "d2.edge.pgToPacket"), (454, 596, "d2.edge.toGenerate"),
    (280, 635, "d2.edge.toValidate"), (542, 635, "d2.edge.toLLM"),
    (612, 205, "d2.edge.rewriteToLLM"), (24, 95, "d2.edge.respond"),
]


def answer_path(lang):
    o = head(840, 812, lang, "d2.desc")
    o.append(text(20, 36, t(lang, "d2.title"), 17, weight=700))
    o.append(text(20, 56, t(lang, "d2.desc"), 12, fill=P["grey"]))
    o.append(text(820, 36, t(lang, "d2.note1"), 11, fill=P["grey"], anchor="end"))
    o.append(text(820, 52, t(lang, "d2.note2"), 11, fill=P["grey"], anchor="end"))
    o += box("external", 320, 76, 200, 52, "client", [t(lang, "d2.client.role")])
    o.append(rect(32, 152, 572, 540, "none", P["gov"]))
    o.append(text(44, 170, t(lang, "d2.zone"), 11, fill=P["govtext"], weight=700))
    o += box("project", 60, 196, 240, 52, "identifiers", [t(lang, "d2.identifiers.role")])
    o += box("project", 336, 196, 240, 52, "rewrite", [t(lang, "d2.rewrite.role")])
    o += leg(52, 308, "bm25", t(lang, "d2.leg.identifier"))
    o += leg(172, 308, "vector", t(lang, "d2.leg.identifier"))
    o += leg(292, 308, "bm25", t(lang, "d2.leg.original"))
    o += leg(412, 308, "vector", t(lang, "d2.leg.original"))
    o += box("project", 176, 404, 280, 52, "fuse_channels", [t(lang, "d2.fuse.role")])
    o += box("core", 116, 500, 400, 72, "packet_for_answer",
             [t(lang, "d2.packet.role1"), t(lang, "d2.packet.role2")])
    o += box("project", 52, 616, 220, 52, "citations.py, numbers.py", [t(lang, "d2.validate.role")])
    o += box("project", 356, 616, 180, 52, "generate_answer", [t(lang, "d2.generate.role")])
    o += box("external", 636, 304, 172, 52, "PostgreSQL", [t(lang, "d2.pg.role")])
    o += box("external", 636, 616, 172, 52, "LLM", [t(lang, "d2.llm.role")])
    o += box("external", 636, 708, 172, 52, "search_log", [t(lang, "d2.log.role")])
    o.append(group(f'fill="none" stroke="{P["ink"]}" stroke-width="1.2"'))
    for d, arrow in ANSWER_EDGES:
        tail = ' marker-end="url(#data)"' if arrow else ""
        o.append(f'      <path d="{d}"{tail}/>')
    o.append("    </g>")
    o.append(group(f'fill="none" stroke="{P["cmd"]}" stroke-width="2"'))
    o += ['      <path d="M446,668 V734 H634" marker-end="url(#cmd)"/>', "    </g>"]
    o.append(group(f'font-size="10.5" fill="{P["ink"]}"'))
    o += [text(x, y, t(lang, k), 10.5) for x, y, k in ANSWER_LABELS]
    o.append("    </g>")
    o.append(group(f'font-size="10.5" fill="{P["cmd"]}"'))
    o += [text(454, 727, t(lang, "d2.edge.writeLog"), 10.5), "    </g>", "  </g>"]
    o += key([("data", t(lang, "d2.key.data")), ("write", t(lang, "d2.key.write")),
              ("project", t(lang, "d2.key.project")), ("core", t(lang, "d2.key.core")),
              ("external", t(lang, "d2.key.external"))], 794)
    o.append("</svg>")
    return "\n".join(o) + "\n"


def write(name, body):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


for theme, tsuf in ((LIGHT, ""), (DARK, ".dark")):
    P.clear()
    P.update(theme)
    for lang, suffix in (("ko", ""), ("en", ".en")):
        write(f"same-information{suffix}{tsuf}.svg", same_information(lang))
        write(f"nexus-answer-path{suffix}{tsuf}.svg", answer_path(lang))
print("ok")
