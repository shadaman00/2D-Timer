#!/usr/bin/env python3
"""StudyPet 소개 영상 — 장면 코드 (16:9 · 7장면 · 나레이션 9문장)

작업 폴더에서:  python scenes.py --sheet  ·  --check  ·  --still 2.0  →  python scenes.py --bake
기획서.md §5 효과 계획 · §7 나레이션을 옮긴 것.
이 영상만의 장치:
  · 고양이는 캔버스 그림 대신 앱의 실제 스프라이트(sheet.png)를 프레임마다 골라 «찍은 뒤» 화면 좌표에 NEAREST 로 그린다
    → 훅의 큰 확대(약 5배)에서도 도트가 흐려지지 않는다. 자리 · 크기는 캔버스 cat 요소 그대로.
  · 장면 4 킥 = 빨리 감기(시계 00:00 → 10:00 · 줄무늬 · ▶▶ 깜빡) → 딱 멈춤.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

SKILL = os.environ.get('MOTION_SKILL') or os.path.expanduser(
    '~/.claude/skills/synced/a0cf4323-3b4c-4564-b60a-ceb9657d55d3_9d41e092-479f-4ce6-ad6e-86118b792462/motion-studio')
sys.path.insert(0, os.path.join(SKILL, 'scripts'))

from core import appear, audio, bake, camera, canvas, fx, kit, motion    # noqa: E402
from core.ease import seg, eo, back, cl                                  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
BOARD = lambda n: os.path.join(HERE, 'canvas', '확정', n)
W, H, FPS = 1920, 1080, 30

# ── 스프라이트 (앱 실물) ──
SHEET = Image.open(os.path.join(HERE, '..', '..', 'assets', 'skins', 'default_pixel_cat', 'sheet.png')).convert('RGBA')
ANIM = {'idle': ([0, 1, 2, 3], 4), 'walk': ([4, 5, 6, 7, 8, 9], 8), 'sit': ([10, 11], 2), 'sleep': ([12, 13, 14, 15], 2),
        'study': ([22, 23, 24, 25, 26, 27], 6), 'celebrate': ([28, 29, 30, 31, 32, 33], 8)}
_FR = {}


def cat_frame(state, lt, speed=1.0):
    frames, fps = ANIM[state]
    i = frames[int(max(0.0, lt) * fps * speed) % len(frames)]
    if i not in _FR: _FR[i] = SHEET.crop((i * 64, 0, i * 64 + 64, 64))
    return _FR[i]


def draw_cat(out, c, box, state, lt, speed=1.0, dx=0.0, dy=0.0, sx=1.0, sy=1.0, alpha=1.0):
    """찍은 화면(out)에 고양이를 카메라 c 기준 화면 좌표로 NEAREST 확대해 붙인다 — 발(아래 가운데) 기준으로 sx · sy"""
    if alpha <= 0: return out
    x, y, w, h = box
    z = c.z
    fw, fh = max(1, int(round(w * z * sx))), max(1, int(round(h * z * sy)))
    spr = cat_frame(state, lt, speed).resize((fw, fh), Image.NEAREST)
    if alpha < 1: spr = spr.copy(); spr.putalpha(spr.getchannel('A').point(lambda v: int(v * alpha)))
    foot_x = (x + w / 2 + dx - c.cx) * z + W / 2
    foot_y = (y + h + dy - c.cy) * z + H / 2
    out.paste(spr, (int(round(foot_x - fw / 2)), int(round(foot_y - fh))), spr)
    return out


# ── 장면 · 대사 ──
SC = [('Main.dc.html', 5.0), ('Scene02.dc.html', 5.5), ('Scene03.dc.html', 6.0), ('Scene04.dc.html', 7.0),
      ('Scene05.dc.html', 6.0), ('Scene06.dc.html', 6.0), ('Scene07.dc.html', 5.0)]
NAMES = ['훅', '클릭', '공부', '자리비움', '기록', '포터블', '마무리']
VO = [(0, 0.5, 'voice/01.wav'), (1, 0.6, 'voice/02.wav'), (2, 0.4, 'voice/03.wav'), (2, 4.83, 'voice/04.wav'),
      (3, 2.5, 'voice/05.wav'), (4, 0.4, 'voice/06.wav'), (5, 0.4, 'voice/07.wav'), (5, 3.15, 'voice/08.wav'),
      (6, 0.5, 'voice/09.wav')]


def _len(p):
    try: return len(audio.read_wav(p)) / audio.SR
    except Exception: return 0.0


DURS = []
for i, (_, base) in enumerate(SC):
    ends = [off + _len(p) + 0.8 for k, off, p in VO if k == i and os.path.exists(p)]
    DURS.append(max([base] + ends))
STARTS = [sum(DURS[:i]) for i in range(len(DURS))]
SCENES = [(s, s + d) for s, d in zip(STARTS, DURS)]
DUR = SCENES[-1][1]
B = [canvas.read_board(BOARD(n)) for n, _ in SC]
KIT = '팝'
K = kit.load(KIT)


def E(k, key):
    """요소를 data-k 이름표로"""
    els = B[k][1]
    for e in els:
        if e['data'].get('k') == key: return e
    raise KeyError(key)


_VAR = {}


def text_as(e, text):
    """같은 요소 · 다른 글자 (시계 · 말풍선 숫자) — 글자마다 한 번만 그린다"""
    key = (id(e), text)
    if key not in _VAR:
        if len(_VAR) > 400: _VAR.clear()
        e2 = {k: v for k, v in e.items() if not k.startswith('_')}; e2['text'] = text; _VAR[key] = e2
    return _VAR[key]


def static(k, keys, tag):
    """처음부터 있는 요소(바탕 · 작업 표시줄 · 별 …)를 한 번만 그린 바탕"""
    root, els = B[k]
    def mk():
        im = canvas.background(root)
        for key in keys:
            lay, x, y = canvas.layer(E(k, key)); im.paste(lay, (x, y), lay)
        return im
    return bake.memo(f'static-{tag}', mk).copy()


TASK = ['taskbar', 'taskline', 'start', 'tray']
CAT_BOX = lambda k: canvas.box(E(k, 'cat'))


# ── 장면 1 · 훅: 고양이 얼굴 화면 가득 → 빠지며 바탕화면 공개 ──
def s1(lt):
    k = 0
    img = static(k, ['star1', 'star2', 'star3', 'star4', 'win', 'winbar', 'winbtn', 'winline1', 'winline2', 'winline3',
                     'app1', 'app2', 'app3'] + TASK, 's1')
    appear.put(img, E(k, 'title1'), seg(lt, 1.3, 1.75), 'left', dist=220)
    appear.put(img, E(k, 'title2'), seg(lt, 1.6, 2.05), 'left', dist=220)
    appear.put(img, E(k, 'badge'), seg(lt, 2.4, 2.75), 'zoom')                 # 내려앉기 (세기 3 장면)
    img = fx.shake(img, lt, 2.72, canvas.background(B[k][0]).getpixel((5, 5)), amp=14, dur=0.3)
    cb = CAT_BOX(k); walk = 1 - eo(seg(lt, 0.0, 2.2))                           # 오른쪽에서 걸어와 제자리에 멈춘다
    face = (cb[0] + 120 * walk + 80, cb[1] + 150, 230, 160)   # 눈 · 볼 · 입 쪽
    c = camera.keys(lt, [(0, camera.on(face, img, fill=1.0)), (0.35, camera.on(face, img, fill=1.0)),
                         (1.55, camera.full(img), '부드럽게')])
    c = camera.drift(c, max(0.0, lt - 1.55), DURS[k] - 1.55, amt=0.03)
    out = camera.shoot(img, c, (W, H))
    st = 'walk' if lt < 2.2 else 'idle'
    return draw_cat(out, c, cb, st, lt, dx=120 * walk)


# ── 장면 2 · 클릭 한 번 → 액션 카드 ──
def s2(lt):
    k = 1
    img = static(k, ['star1', 'star2', 'app1', 'app2'] + TASK, 's2')
    appear.put(img, E(k, 'title'), seg(lt, 0.1, 0.5), 'fade')
    kc = seg(lt, 1.15, 1.5)
    for key in ('card', 'head'): appear.put(img, E(k, key), kc, 'pop')
    for key in ('primary', 'icon', 'plabel'): appear.put(img, E(k, key), seg(lt, 1.4, 1.7), 'up', dist=40)
    for key in ('secA', 'secB'): appear.put(img, E(k, key), seg(lt, 1.55, 1.85), 'up', dist=40)
    for key in ('f1', 'f2', 'f3'): appear.put(img, E(k, key), seg(lt, 1.7, 2.0), 'up', dist=40)
    chip = E(k, 'chip')
    if lt < 3.6: appear.put(img, chip, seg(lt, 3.0, 3.4), 'right')
    else: motion.put(img, chip, s=motion.pulse(lt, 3.6))                       # 강조 하나: 칩 맥박
    group = (560, 250, 1340, 760)
    c = camera.keys(lt, [(0, camera.full(img)), (1.9, camera.full(img)), (2.9, camera.on(group, img, fill=0.97), '부드럽게')])
    c = camera.drift(c, max(0.0, lt - 2.9), DURS[k] - 2.9, amt=0.02)
    out = camera.shoot(img, c, (W, H))
    squash = 0.9 if 0.95 <= lt < 1.12 else 1.0
    draw_cat(out, c, CAT_BOX(k), 'idle', lt, sx=1 / squash if squash < 1 else 1, sy=squash)
    # 커서: 오른쪽 아래에서 고양이로 → 톡 (고양이 위에 보이도록 찍은 화면 위에 그린다) · 카드가 열리면 사라짐
    cur = E(k, 'cursor'); u = eo(seg(lt, 0.2, 0.9)); ca = 1 - seg(lt, 2.0, 2.4)
    if ca > 0:
        lay, x, y = canvas.layer(cur)
        press = 0.86 if 0.95 <= lt < 1.1 else 1.0
        sw, sh = max(1, int(lay.width * c.z * press)), max(1, int(lay.height * c.z * press))
        l2 = lay.resize((sw, sh), Image.NEAREST)
        if ca < 1: l2.putalpha(l2.getchannel('A').point(lambda v: int(v * ca)))
        sx_ = (x + 320 * (1 - u) - c.cx) * c.z + W / 2; sy_ = (y + 160 * (1 - u) - c.cy) * c.z + H / 2
        out.paste(l2, (int(sx_), int(sy_)), l2)
    return out


# ── 장면 3 · 같이 공부: idle → study · 말풍선 시계 · 뽀모도로 링 ──
def s3(lt):
    k = 2
    img = static(k, ['star1', 'star2', 'app1'] + TASK, 's3')
    appear.put(img, E(k, 'title'), seg(lt, 0.2, 0.6), 'fade')
    bub = E(k, 'bubble')
    sec = 10 + min(5, max(0, int(lt - 1.2)))
    appear.put(img, text_as(bub, f'알고리즘 | 01:24:{sec:02d}'), seg(lt, 1.1, 1.45), 'pop')
    appear.put(img, E(k, 'ringtrack'), seg(lt, 4.7, 5.0), 'fade')
    motion.draw_on(img, E(k, 'ringfocus'), seg(lt, 4.9, 5.9))
    motion.draw_on(img, E(k, 'ringbreak'), seg(lt, 5.9, 6.3))
    appear.put(img, E(k, 'ringlabel'), seg(lt, 5.2, 5.5), 'fade')
    motion.spin_in(img, E(k, 'chipfocus'), seg(lt, 5.6, 6.0))
    motion.spin_in(img, E(k, 'chipbreak'), seg(lt, 6.4, 6.8))
    left = (130, 350, 780, 650); right = (1040, 260, 640, 640)
    c = camera.keys(lt, [(0, camera.on(left, img, fill=0.85)), (4.4, camera.on(left, img, fill=0.85)),
                         (5.3, camera.on(right, img, fill=0.92), '부드럽게'), (7.0, camera.on(right, img, fill=0.92)),
                         (7.9, camera.full(img), '부드럽게')])
    out = camera.shoot(img, c, (W, H))
    cb = CAT_BOX(k)
    if lt < 0.9: return draw_cat(out, c, cb, 'idle', lt)
    s = back(seg(lt, 0.9, 1.15)) if lt < 1.15 else 1.0                        # «통» 바뀜
    return draw_cat(out, c, cb, 'study', lt - 0.9, sx=0.8 + 0.2 * s, sy=0.8 + 0.2 * s)


# ── 장면 4 · 킥: 빨리 감기 → 딱 멈춤 → 자리 비움 창 ──
FF_END = 2.2


def s4(lt):
    k = 3
    root = B[k][0]
    img = static(k, ['star1', 'star2', 'idle'] + TASK, 's4')
    clock = E(k, 'clock')
    v = 600 * (seg(lt, 0.15, FF_END) ** 1.6)                                    # 가속하며 감김 → 10:00 에 딱
    m, s_ = int(v) // 60, int(v) % 60
    motion.put(img, text_as(clock, f'{m:02d}:{s_:02d}'))
    if lt < FF_END:
        if int(lt * 6) % 2 == 0: motion.put(img, E(k, 'ff'))                    # ▶▶ 깜빡
    else:
        appear.put(img, E(k, 'ff'), seg(lt, FF_END, FF_END + 0.25), 'pop')
    appear.put(img, E(k, 'title'), seg(lt, 2.6, 3.0), 'right', dist=200)
    km = seg(lt, 3.4, 3.85)
    for key in ('modal', 'mbar', 'mbartxt', 'mtext', 'bexclude', 'binclude'):
        appear.put(img, E(k, key), km, 'down', dist=220, ease=back)
    img = fx.shake(img, lt, FF_END, root['bg'], amp=18, dur=0.32)
    img = fx.shake(img, lt, 3.85, root['bg'], amp=8, dur=0.2)
    a0, a1 = camera.at(830, 520, 1.16), camera.at(830, 520, 1.26)              # 시계 · 고양이 쪽 (아트보드 안쪽만 보이게)
    c = camera.keys(lt, [(0, a0), (FF_END, a0), (FF_END, a1), (2.6, a0, '부드럽게'),
                         (3.2, a0), (3.9, camera.full(img), '부드럽게')])
    c = camera.handheld(c, lt, amp=3)
    out = camera.shoot(img, c, (W, H))
    draw_cat(out, c, CAT_BOX(k), 'sleep', lt, speed=6.0 if lt < FF_END else 1.0)
    if lt < FF_END:                                                            # 빨리 감기 화면: 줄무늬 + 살짝 색 밀림
        a = np.asarray(out).astype(np.int16)
        a[::6] = (a[::6] * 0.6).astype(np.int16)
        shift = 6 + int(4 * math.sin(lt * 40))
        a[:, shift:, 0] = a[:, :-shift, 0]
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    return out


# ── 장면 5 · 기록: 창이 떨어지고 막대가 자람 ──
def s5(lt):
    k = 4
    img = static(k, ['star1'] + TASK, 's5')
    appear.put(img, E(k, 'title1'), seg(lt, 0.3, 0.65), 'left', dist=160)
    appear.put(img, E(k, 'title2'), seg(lt, 0.5, 0.85), 'left', dist=160)
    kw = seg(lt, 0.1, 0.55)
    for key in ('win', 'wbar', 'wbartxt', 'tab1', 'tab2', 'tab3'):
        appear.put(img, E(k, key), kw, 'down', dist=260, ease=back)
    if lt < 4.0: appear.put(img, E(k, 'csv'), kw, 'down', dist=260, ease=back)
    else: motion.put(img, E(k, 'csv'), s=motion.pulse(lt, 4.0))               # 강조 하나: CSV 맥박
    for i, (l, b) in enumerate((('l1', 'b1'), ('l2', 'b2'), ('l3', 'b3'))):
        t0 = 1.1 + i * 0.35
        appear.put(img, E(k, l), seg(lt, t0, t0 + 0.25), 'fade')
        appear.put(img, E(k, b), seg(lt, t0 + 0.05, t0 + 0.6), 'wipe', dir='left')
    appear.put(img, E(k, 'goal'), seg(lt, 2.2, 2.5), 'wipe', dir='up')
    appear.put(img, E(k, 'goaltxt'), seg(lt, 2.3, 2.55), 'fade')
    appear.put(img, E(k, 'rate'), seg(lt, 3.6, 3.9), 'fade')
    if 2.6 <= lt < 3.3:                                                        # 주간 탭 반짝
        d = ImageDraw.Draw(img)
        fx.sparkles(d, lt, [(1030, 232, 2.6, 26), (884, 290, 2.75, 18)])
    top = (650, 110, 1210, 320); bars = (650, 330, 1210, 460)
    c = camera.keys(lt, [(0, camera.on(top, img, fill=0.9)), (0.9, camera.on(top, img, fill=0.9)),
                         (1.6, camera.on(bars, img, fill=0.9), '부드럽게'), (2.7, camera.on(bars, img, fill=0.9)),
                         (3.6, camera.full(img), '부드럽게')])
    out = camera.shoot(img, c, (W, H))
    return draw_cat(out, c, CAT_BOX(k), 'sit', lt, alpha=seg(lt, 0.2, 0.5))


# ── 장면 6 · 포터블: 폴더가 PC → USB → 다른 PC ──
def s6(lt):
    k = 5
    img = static(k, ['star1', 'pc1', 'pc1neck', 'pc1base', 'pc2', 'pc2neck', 'pc2base', 'usb', 'usbplug'] + TASK, 's6')
    appear.put(img, E(k, 'title'), seg(lt, 0.1, 0.5), 'fade')
    appear.put(img, E(k, 'usbtxt'), seg(lt, 0.6, 0.9), 'fade')
    appear.put(img, E(k, 'path'), seg(lt, 0.5, 1.4), 'wipe', dir='left')
    appear.put(img, E(k, 'sub'), seg(lt, 3.1, 3.5), 'up', dist=40)
    if lt >= 5.2: appear.put(img, E(k, 'ghost'), 1, 'fade')
    # 폴더: PC1 화면 → USB 위 → PC2 화면 (캔버스 자리 = 도착 자리)
    p0, p1, p2 = (-1220, 0), (-610, -10), (0, 0)
    u1 = eo(seg(lt, 3.3, 4.1)); u2 = eo(seg(lt, 4.3, 5.1))
    if lt < 4.2: off = (p0[0] + (p1[0] - p0[0]) * u1, p0[1] + (p1[1] - p0[1]) * u1 - 60 * math.sin(math.pi * u1))
    else: off = (p1[0] + (p2[0] - p1[0]) * u2, p1[1] + (p2[1] - p1[1]) * u2 - 60 * math.sin(math.pi * u2))
    fa = seg(lt, 0.8, 1.1)
    for key in ('ftab', 'folder'): motion.put(img, E(k, key), alpha=fa, off=off)
    appear.put(img, E(k, 'fname'), seg(lt, 5.15, 5.4), 'fade')
    appear.put(img, E(k, 'data'), seg(lt, 5.4, 5.75), 'left', dist=120)
    appear.put(img, E(k, 'files'), seg(lt, 5.7, 6.0), 'fade')
    pc1 = (40, 180, 1330, 750); mid = (300, 180, 1330, 750); pc2 = (560, 180, 1330, 750)   # 훑기 (1.44배)
    c = camera.keys(lt, [(0, camera.full(img)), (2.9, camera.full(img)), (3.4, camera.on(pc1, img, fill=1.0), '부드럽게'),
                         (4.15, camera.on(mid, img, fill=1.0), '부드럽게'), (5.1, camera.on(pc2, img, fill=1.0), '부드럽게'),
                         (6.0, camera.on(pc2, img, fill=1.0)), (6.6, camera.full(img), '부드럽게')])
    out = camera.shoot(img, c, (W, H))
    return draw_cat(out, c, CAT_BOX(k), 'sit', lt)


# ── 장면 7 · 마무리: 장면 1과 같은 자리(매치 컷) → 로고 ──
def s7(lt):
    k = 6
    img = static(k, ['star1', 'star2', 'star3', 'star4', 'app1', 'app2', 'app3'] + TASK, 's7')
    appear.put(img, E(k, 'logo'), seg(lt, 0.3, 0.7), 'pop')
    appear.put(img, E(k, 'tagline'), seg(lt, 0.8, 1.15), 'up', dist=60)
    appear.put(img, E(k, 'desc'), seg(lt, 1.5, 1.9), 'fade')
    d = ImageDraw.Draw(img)
    fx.sparkles(d, lt, [(1200, 280, 0.7, 34), (180, 260, 0.85, 24), (1100, 470, 1.0, 22), (1500, 620, 1.3, 28),
                        (1760, 700, 1.6, 20), (1290, 840, 2.1, 22)])
    grp = (90, 240, 1260, 520)
    c = camera.keys(lt, [(0, camera.full(img)), (0.4, camera.full(img)), (2.0, camera.on(grp, img, fill=0.98), '부드럽게'),
                         (3.4, camera.on(grp, img, fill=0.98)), (4.4, camera.full(img), '부드럽게')])
    out = camera.shoot(img, c, (W, H))
    return draw_cat(out, c, CAT_BOX(k), 'celebrate', lt)


SCENE_FN = [s1, s2, s3, s4, s5, s6, s7]
PLAN = [
    {'level': 3, 'camera': ['빠지며 공개', '천천히 흐르기'], 'enter': ['left', 'zoom'], 'emph': ['shake'], 'kick': None,
     'borrow': '배지 착지 흔들림(shake) — 훅 봉우리 한 번'},
    {'level': 2, 'camera': ['밀고 들어가기'], 'enter': ['fade', 'pop', 'up', 'right'], 'emph': ['pulse'], 'kick': None},
    {'level': 1, 'camera': ['시선 옮기기'], 'enter': ['fade', 'pop', 'draw_on', 'spin_in'], 'emph': [], 'kick': None,
     'borrow': '뽀모도로 링 선 그려지기(draw_on) — 링이 차오르는 모양이 내용'},
    {'level': 3, 'camera': ['손에 든 카메라', '밀고 들어가기'], 'enter': ['down', 'right'], 'emph': ['shake'], 'kick': '빨리 감기',
     'borrow': '킥 «빨리 감기»(10분 압축 · 원문 숫자) · 창 떨어짐(down) · 손에 든 카메라'},
    {'level': 2, 'camera': ['훑기'], 'enter': ['left', 'down', 'wipe'], 'emph': ['pulse'], 'kick': None,
     'borrow': '막대 자람 = wipe · 창 떨어짐 = down'},
    {'level': 1, 'camera': ['훑기'], 'enter': ['fade', 'wipe', 'up', 'left'], 'emph': [], 'kick': None, 'borrow': '점선 길 wipe'},
    {'level': 2, 'camera': ['밀고 들어가기'], 'enter': ['pop', 'up'], 'emph': ['sparkles'], 'kick': None,
     'borrow': '매치 컷(장면 1 구도) — 경계는 그냥 컷'},
]
EDIT = K.cuts([p['level'] for p in PLAN[1:]], names=NAMES)
EDIT[6] = ('cut', 0.04, {})                                                    # 매치 컷


def render(k, t, xf=0.0):
    lt = t - STARTS[k] + (xf / 2 if k > 0 else 0)
    return SCENE_FN[k](lt)


def frame(t):
    k = max(i for i, s in enumerate(STARTS) if s <= t + 1e-9)
    for j in (k, k + 1):
        if j in EDIT:
            name, xf, opt = EDIT[j]
            if abs(t - STARTS[j]) < xf / 2:
                a = render(j - 1, STARTS[j] - xf / 2, EDIT.get(j - 1, ('', 0))[1]); b_ = render(j, t, xf)
                return K.finish(K.edit(name, a, b_, (t - (STARTS[j] - xf / 2)) / xf, **opt), t)
    return K.finish(render(k, t, EDIT.get(k, ('', 0, {}))[1]), t)


def build_audio(path):
    """배경음 «레트로 게임» + 효과음(레트로 게임 묶음 · 이름으로 몇 개) + 대사"""
    from core import sfx as SFX
    S = SFX.Kit('레트로 게임'); trk = audio.new_track(DUR)
    T = lambda k, lt: STARTS[k] + lt
    for j, (name, xf, _) in EDIT.items():
        if name == 'impact': SFX.put_sfx(trk, 'boom_808', STARTS[j], 0.6)
        elif name != 'cut': S.put(trk, 'cut', STARTS[j] - min(0.3, xf / 2), 0.35)
    SFX.put_sfx(trk, 'boom_808', T(0, 2.72), 0.6)                               # 배지 쾅
    SFX.put_sfx(trk, 'ui_click', T(1, 0.97), 0.55)                              # 커서 톡
    S.put(trk, 'enter', T(1, 1.18), 0.35)                                       # 카드
    S.put(trk, 'emph', T(1, 3.6), 0.35)                                         # 칩
    SFX.put_sfx(trk, 'bloop_up', T(2, 0.9), 0.4)                                # 공부 모션으로 «통»
    S.put(trk, 'emph', T(2, 5.0), 0.3)                                          # 링
    SFX.put_sfx(trk, 'counter_up', T(3, 0.2), 0.4)                              # 빨리 감기 틱틱
    SFX.put_sfx(trk, 'record_scratch', T(3, FF_END - 0.05), 0.35)               # 딱 멈춤
    SFX.put_sfx(trk, 'boom_808', T(3, FF_END), 0.55)
    SFX.put_sfx(trk, 'soft_thud', T(3, 3.85), 0.5)                              # 창 툭
    for i in range(3): S.put(trk, 'tick', T(4, 1.15 + i * 0.35), 0.3)           # 막대
    S.put(trk, 'emph', T(4, 2.6), 0.3)
    SFX.put_sfx(trk, 'laser', T(5, 3.3), 0.3); SFX.put_sfx(trk, 'laser', T(5, 4.3), 0.3)   # 폴더 이동
    S.put(trk, 'enter', T(5, 5.4), 0.35)
    SFX.put_sfx(trk, 'level_up', T(6, 0.3), 0.45)                               # 로고
    S.put(trk, 'done', DUR - 1.2, 0.4)
    try:
        secs = [(0, 1.6, 'sting', {}), (1.6, STARTS[3], 1, {}), (STARTS[3], STARTS[3] + FF_END, 'build', {}),
                (STARTS[3] + FF_END, STARTS[6], 2, {'hits': [STARTS[3] + FF_END]}), (STARTS[6], DUR, 'outro', {'hit': DUR - 1.2})]
        bg = audio.bgm(secs, DUR, style='레트로 게임')
    except SystemExit as e:
        print(e); bg = None
    voices = [(STARTS[k] + off, p) for k, off, p in VO if os.path.exists(p)]
    return audio.mixdown(DUR, path, bg, trk, voices)


def _win_init(step):
    """Windows 굽기 일꾼 — 다시 읽힌 이 장면 코드(__mp_main__)를 엔진에 알려 준다"""
    bake._M = sys.modules['__mp_main__']; bake._STEP = step


def _win_frames(M, lo, hi, out, workers=None, chunk=18, crf=18, preset='faster', step=1):
    """bake.frames 와 같은 일 — Windows 에는 fork 가 없어 spawn 으로 일꾼을 띄운다 (스킬 파일은 고치지 않음)"""
    import multiprocessing as mp
    import subprocess
    bake._M = M; bake._STEP = step
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    p = subprocess.Popen(bake.FF + ['-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{M.W}x{M.H}', '-r', str(M.FPS / step), '-i', '-',
                                    '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p', out], stdin=subprocess.PIPE)
    workers = workers or int(os.environ.get('MOTION_WORKERS', 0)) or max(1, min(8, (os.cpu_count() or 2) - 1))
    with mp.get_context('spawn').Pool(workers, initializer=_win_init, initargs=(step,)) as pool:
        for i, b in enumerate(pool.imap(bake._work, range(lo, hi), chunksize=chunk)):
            p.stdin.write(b)
            if (i + 1) % (M.FPS * 5) == 0: print(f'  {lo + i + 1}/{hi} 프레임', flush=True)
    p.stdin.close(); p.wait()
    return out


if __name__ == '__main__':
    if os.name == 'nt': bake.frames = _win_frames
    bake.cli(sys.modules[__name__], out=os.path.join(HERE, 'out', 'StudyPet_소개.mp4'), audio=build_audio)
    if canvas.missing: print('⚠ 못 찾음:', ' · '.join(sorted(canvas.missing)))
