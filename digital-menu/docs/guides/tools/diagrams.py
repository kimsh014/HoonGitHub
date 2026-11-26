# 안내서 그림(SVG)을 만든다. 사용: python3 diagrams.py  → ../images/*.svg
# 그림을 고칠 때는 SVG를 직접 고치지 말고 이 파일을 고쳐 다시 만든다.
import os
from xml.sax.saxutils import escape

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')
RED, DARK, GRAY, LIGHT, GREEN, BLUE, AMBER = '#c8102e', '#1f2328', '#6e7781', '#f3f4f6', '#1a7f37', '#0969da', '#bf8700'
FONT = "'Noto Sans KR','Malgun Gothic','Apple SD Gothic Neo',sans-serif"


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.parts = w, h, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=16, color=DARK, weight='normal', anchor='middle'):
        lines = s.split('\n')
        for i, line in enumerate(lines):
            yy = y + (i - (len(lines) - 1) / 2) * size * 1.3
            self.add(f'<text x="{x}" y="{yy:.1f}" font-size="{size}" fill="{color}" font-weight="{weight}" '
                     f'text-anchor="{anchor}" dominant-baseline="central">{escape(line)}</text>')

    def box(self, x, y, w, h, label='', fill='#fff', stroke=DARK, size=16, color=DARK, weight='normal', r=10, dash=False, sw=2):
        d = ' stroke-dasharray="6 5"' if dash else ''
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
        if label:
            self.text(x + w / 2, y + h / 2, label, size, color, weight)

    def circle(self, x, y, r, label, fill=RED, color='#fff', size=18):
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>')
        self.text(x, y, label, size, color, 'bold')

    def arrow(self, pts, color=DARK, label='', size=14, dash=False, lx=None, ly=None, sw=2.5):
        d = ' stroke-dasharray="7 6"' if dash else ''
        p = ' '.join(f'{x},{y}' for x, y in pts)
        mid = {DARK: 'a-dark', RED: 'a-red', GRAY: 'a-gray', GREEN: 'a-green', BLUE: 'a-blue', AMBER: 'a-amber'}[color]
        self.add(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}"{d} marker-end="url(#{mid})"/>')
        if label:
            (x1, y1), (x2, y2) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
            self.text(lx if lx is not None else (x1 + x2) / 2, ly if ly is not None else (y1 + y2) / 2 - 14, label, size, color, 'bold')

    def save(self, name):
        markers = ''.join(
            f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            for i, c in [('a-dark', DARK), ('a-red', RED), ('a-gray', GRAY), ('a-green', GREEN), ('a-blue', BLUE), ('a-amber', AMBER)])
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
               f'font-family="{FONT}"><defs>{markers}</defs><rect width="100%" height="100%" fill="#fff"/>'
               + ''.join(self.parts) + '</svg>\n')
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            f.write(svg)


def tv(s, x, y, w=150, h=86, label='', sub=''):
    s.box(x, y, w, h, '', fill='#111', stroke='#111', r=6)
    s.box(x + 8, y + 8, w - 16, h - 16 - (18 if sub else 0), label, fill='#2b2f36', stroke='#2b2f36', color='#fff', size=15, r=3)
    if sub:
        s.add(f'<rect x="{x + 8}" y="{y + h - 26}" width="{w - 16}" height="18" fill="{RED}"/>')
        s.text(x + w / 2, y + h - 17, sub, 12, '#fff', 'bold')


def overview():
    s = Svg(980, 470)
    s.text(490, 28, '번호 호출 메뉴판은 이렇게 움직입니다 (1차)', 22, DARK, 'bold')
    # 위: 주문
    s.box(30, 70, 190, 80, '판매 프로그램·키오스크\n(지금 쓰는 그대로)', fill=LIGHT)
    s.box(280, 70, 160, 80, '번호표 출력\n주문번호 105', fill=LIGHT)
    s.box(500, 70, 160, 80, '손님은 번호표를\n들고 기다림', fill=LIGHT)
    s.arrow([(220, 110), (278, 110)])
    s.arrow([(440, 110), (498, 110)])
    s.circle(48, 70, 16, '1')
    # 가운데: 준비 완료
    s.box(30, 220, 190, 90, '음식 준비 끝\n직원이 키패드로\n1 0 5 Enter', fill='#fff5f5', stroke=RED)
    s.circle(48, 220, 16, '2')
    s.box(300, 210, 230, 110, 'POS기\n(메뉴판 서버가 늘 켜져 있음)\n127.0.0.1:8090', fill='#fff', stroke=DARK, weight='bold')
    s.arrow([(220, 265), (298, 265)], RED, '번호 보내기', lx=259, ly=240, size=13)
    s.box(590, 235, 110, 60, '공유기', fill=LIGHT)
    s.arrow([(530, 265), (588, 265)])
    tv(s, 770, 175, 180, 100, '메뉴판', '준비된 번호 105')
    tv(s, 770, 300, 180, 100, '메뉴판', '준비된 번호 105')
    s.arrow([(700, 255), (768, 225)])
    s.arrow([(700, 275), (768, 350)])
    s.text(860, 160, '천장 TV (0.5초 안)', 14, RED, 'bold')
    s.circle(788, 175, 16, '3')
    # 아래: 메뉴 수정
    s.box(270, 370, 290, 70, '사장님: POS기 화면이나 휴대폰으로\n메뉴·사진·가격·품절 고치기', fill='#f0f7ff', stroke=BLUE, size=14)
    s.arrow([(415, 370), (415, 322)], BLUE, '저장하면 TV에 바로', lx=520, ly=345)
    s.text(860, 430, '부른 번호는 10분 뒤 저절로 빠집니다', 13, GRAY)
    s.save('overview.svg')


def network():
    s = Svg(980, 520)
    s.text(490, 28, '매장 네트워크: TV와 POS기는 같은 공유기, 손님은 게스트 와이파이', 21, DARK, 'bold')
    s.box(400, 60, 180, 50, '인터넷', fill=LIGHT, stroke=GRAY, color=GRAY)
    s.box(390, 160, 200, 70, '공유기\n(ipTIME 등)', fill='#fff', weight='bold')
    s.arrow([(490, 110), (490, 158)], GRAY)
    # 매장망
    s.box(30, 280, 600, 210, '', fill='#f6fff8', stroke=GREEN, dash=True)
    s.text(330, 470, '매장망 (같은 공유기 안)', 15, GREEN, 'bold')
    s.box(60, 330, 170, 100, 'POS기\n주소 고정\n192.168.0.10', fill='#fff', weight='bold')
    s.text(145, 445, '방화벽 8090: 같은 공유기만', 12, GREEN)
    tv(s, 270, 335, 150, 86, 'TV 1')
    tv(s, 450, 335, 150, 86, 'TV 2')
    s.text(345, 440, '랜선 권장', 13, GREEN, 'bold')
    s.text(525, 440, '와이파이면 매장용에', 13, GREEN, 'bold')
    s.arrow([(450, 230), (145, 328)], GREEN)
    s.arrow([(480, 230), (345, 333)], GREEN)
    s.arrow([(510, 230), (525, 333)], GREEN)
    # 게스트
    s.box(670, 280, 280, 210, '', fill='#fff5f5', stroke=RED, dash=True)
    s.text(810, 470, '게스트 와이파이 (손님용)', 15, RED, 'bold')
    s.box(735, 340, 150, 70, '손님 휴대폰', fill='#fff', stroke=RED)
    s.arrow([(560, 230), (805, 338)], RED)
    s.text(810, 430, '메뉴판 서버에 못 들어옴', 13, RED, 'bold')
    s.add(f'<line x1="640" y1="360" x2="700" y2="420" stroke="{RED}" stroke-width="5"/>')
    s.add(f'<line x1="700" y1="360" x2="640" y2="420" stroke="{RED}" stroke-width="5"/>')
    s.box(620, 160, 330, 70, '공유기에 "바꾸기 전 A/S 문의" 스티커\n공유기를 바꾸면 주소 예약이 사라짐', fill='#fffbe6', stroke=AMBER, size=13)
    s.save('network.svg')


def install_order():
    steps = [
        ('POS기에 서버 설치', 'install-server.bat', '20분'),
        ('POS기 주소 고정', '공유기 DHCP 예약', '5분'),
        ('정전 뒤 자동 켜짐', 'BIOS 설정', '5분'),
        ('TV 앱 설치', '바닥에서, USB 연결', '10분'),
        ('화면 번호·방향 맞추기', '라벨 붙이기', '5분'),
        ('TV 천장에 달기', '랜선·전원 정리', ''),
        ('POS기에서 TV 확인', 'devices.html', '5분'),
        ('번호 키패드 설치', '준비 중', ''),
        ('사장님께 인계', '설명서·스티커', '10분'),
    ]
    s = Svg(980, 400)
    s.text(490, 28, '설치 순서 한눈에 (위에서 아래, 왼쪽에서 오른쪽)', 22, DARK, 'bold')
    for i, (a, b, t) in enumerate(steps):
        col, row = i % 3, i // 3
        x, y = 40 + col * 320, 60 + row * 110
        ceiling = i == 5
        soon = b == '준비 중'
        s.box(x, y, 270, 82, '', fill='#fff5f5' if ceiling else ('#f6f8fa' if soon else '#fff'),
              stroke=RED if ceiling else (GRAY if soon else DARK), dash=soon)
        s.circle(x + 30, y + 41, 18, str(i + 1), fill=GRAY if soon else RED)
        s.text(x + 60, y + 30, a, 17, DARK, 'bold', 'start')
        s.text(x + 60, y + 56, b + (f' · {t}' if t else ''), 14, AMBER if soon else GRAY, 'bold' if soon else 'normal', 'start')
        if col < 2:
            s.arrow([(x + 272, y + 41), (x + 318, y + 41)], GRAY)
    s.text(490, 385, '5번까지 바닥에서 끝내고 6번에서 천장에 답니다. 달고 나면 7번부터는 사다리 없이 POS기에서 합니다.', 15, RED, 'bold')
    s.save('install-order.svg')


def ceiling_fix():
    s = Svg(980, 470)
    s.text(490, 28, '천장 TV를 손봐야 할 때: 사다리는 맨 마지막', 22, DARK, 'bold')
    s.box(340, 60, 300, 60, 'TV가 TV 관리 화면 목록에\n"연결됨"으로 보이나요?', fill=LIGHT, weight='bold', size=15)
    # 예
    s.arrow([(490, 120), (490, 150), (200, 150), (200, 178)], GREEN, '예', lx=340, ly=138)
    s.box(40, 180, 320, 150, '', fill='#f6fff8', stroke=GREEN)
    s.text(200, 205, '① POS기에서 바로', 17, GREEN, 'bold')
    s.text(60, 272, 'devices.html 에서\n화면 번호·배율·방향·밝기·서버 주소\n지금 화면 보기 · 앱 다시 켜기\nA/S 연결(adb) 열기', 14, DARK, anchor='start')
    # 아니오
    s.arrow([(640, 90), (780, 90), (780, 178)], RED, '아니오', lx=720, ly=76)
    s.box(620, 180, 320, 150, '', fill='#fff5f5', stroke=RED)
    s.text(780, 205, '② USB 메모리 꽂기', 17, RED, 'bold')
    s.text(640, 272, 'devices.html 에서 menuboard.txt 받기\nUSB 맨 위에 저장 → TV 보드에 꽂기\n몇 초 안에 적용, 화면 아래 결과 표시\n(보드 USB 단자가 손 닿는 곳일 때)', 14, DARK, anchor='start')
    s.arrow([(780, 330), (780, 370), (650, 370)], GRAY, '안 되면', lx=740, ly=356)
    s.box(330, 350, 320, 90, '', fill='#fffbe6', stroke=AMBER)
    s.text(490, 372, '③ 리모컨 · 마지막에 사다리', 17, AMBER, 'bold')
    s.text(490, 412, '메뉴판에서 리모컨 확인 버튼 2초 → 설정 화면\n그래도 안 되면 사다리 + USB 연결로 다시 설치', 13, DARK)
    s.save('ceiling-fix.svg')


def tv_trouble():
    s = Svg(980, 560)
    s.text(490, 28, 'TV에 메뉴판이 안 나올 때 차례대로', 22, DARK, 'bold')
    qs = [
        ('TV 화면에 무엇이 보이나요?', ''),
    ]
    rows = [
        ('검은 화면·방송 화면', '리모컨으로 입력(HDMI)을 메뉴판 보드 쪽으로.\nTV 전원·HDMI 선 확인.', DARK),
        ('"서버를 찾지 못했습니다"\n설정 화면', 'POS기가 켜져 있나? → POS기에서 127.0.0.1:8090/?screen=1 열기\n같은 공유기인가? 손님 와이파이에 붙지 않았나?', RED),
        ('매장 이름만 크게', 'TV가 없는 화면 번호를 띄우는 중.\n수정 화면 "화면 구성"의 경고를 보고 번호를 맞춤', AMBER),
        ('메뉴는 나오는데 옛 메뉴', '끊겨서 마지막 저장 화면을 띄우는 중(최대 10분 전 모습).\nPOS기 서버·공유기 확인, 붙으면 저절로 새로 고침', BLUE),
        ('설정 화면이 떠 있음', '누가 리모컨 확인을 2초 누름.\n2분 지나면 저절로 메뉴판으로 돌아감', GRAY),
    ]
    s.box(330, 55, 320, 50, qs[0][0], fill=LIGHT, weight='bold')
    for i, (a, b, c) in enumerate(rows):
        y = 130 + i * 84
        s.box(40, y, 270, 68, a, fill='#fff', stroke=c, color=c, weight='bold', size=15)
        s.arrow([(312, y + 34), (358, y + 34)], c)
        s.box(360, y, 580, 68, '', fill='#fff', stroke='#d0d7de')
        s.text(380, y + 34, b, 14, DARK, anchor='start')
    s.add(f'<polyline points="490,105 490,118 175,118 175,128" fill="none" stroke="{GRAY}" stroke-width="2"/>')
    s.save('tv-trouble.svg')


def owner_day():
    s = Svg(980, 300)
    s.text(490, 28, '사장님의 하루', 22, DARK, 'bold')
    items = [
        ('아침', '전원만 켜기', 'POS기·TV 전원을 켜면\n메뉴판이 저절로 뜹니다', RED),
        ('영업 전', '품절 확인', '수정 화면 맨 위\n"지금 품절" 보고 풀기', AMBER),
        ('영업 중', '번호 부르기', '번호 + Enter\n잘못 불렀으면 빼기', GREEN),
        ('한가할 때', '메뉴·가격·사진', '고치고 그 줄의 "저장"\nTV 미리보기로 확인', BLUE),
        ('마감', 'Windows 종료', 'POS기는 시스템 종료로\n매일 자동 백업됨', GRAY),
    ]
    for i, (t, a, b, c) in enumerate(items):
        x = 30 + i * 190
        s.box(x, 60, 170, 210, '', fill='#fff', stroke=c, sw=2.5)
        s.add(f'<rect x="{x}" y="60" width="170" height="40" rx="10" fill="{c}"/><rect x="{x}" y="85" width="170" height="15" fill="{c}"/>')
        s.text(x + 85, 80, t, 17, '#fff', 'bold')
        s.text(x + 85, 135, a, 17, c, 'bold')
        s.text(x + 85, 205, b, 14, DARK)
        if i < 4:
            s.arrow([(x + 171, 165), (x + 189, 165)], GRAY, sw=2)
    s.save('owner-day.svg')


def keypad():
    s = Svg(980, 420)
    s.text(490, 28, '번호 키패드 쓰는 법 (키패드 앱은 준비 중, 시험 뒤 설치)', 21, DARK, 'bold')
    keys = [
        ['Num', '/', '*', '-'],
        ['7', '8', '9', '+'],
        ['4', '5', '6', ''],
        ['1', '2', '3', 'Enter'],
        ['0', '', '.', ''],
    ]
    kx, ky, k = 60, 60, 66
    colors = {'/': AMBER, '*': AMBER, '-': RED, '+': BLUE, 'Enter': GREEN, '.': AMBER}
    for r, row in enumerate(keys):
        for c, key in enumerate(row):
            if key == '':
                continue
            w, h = k - 8, k - 8
            if key == '+' or key == 'Enter':
                h = 2 * k - 8
            if key == '0':
                w = 2 * k - 8
            col = colors.get(key, DARK)
            s.box(kx + c * k, ky + r * k, w, h, key, fill='#fff' if col == DARK else col, stroke=col,
                  color=DARK if col == DARK else '#fff', weight='bold', size=18 if len(key) < 3 else 14, r=8)
    rows = [
        ('1 0 5  Enter', '105번 부르기 → TV에 크게', GREEN),
        ('+ 1 0 5  Enter', '105번 다시 부르기 (손님이 안 오실 때)', BLUE),
        ('- 1 0 5  Enter', '105번 TV에서 빼기 (잘못 불렀을 때)', RED),
        ('-  Enter', '방금 부른 번호 빼기', RED),
        ('.  /  *', '. 한 자리 지움 · / * 모두 지움', AMBER),
    ]
    for i, (a, b, c) in enumerate(rows):
        y = 70 + i * 62
        s.box(400, y, 190, 46, a, fill='#fff', stroke=c, color=c, weight='bold', size=17)
        s.text(610, y + 23, b, 16, DARK, anchor='start')
    s.text(660, 395, '멀리 떨어진 번호·이미 TV에 있는 번호는 Enter를 한 번 더 누르라고 묻습니다.', 13, GRAY)
    s.save('keypad.svg')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for f in (overview, network, install_order, ceiling_fix, tv_trouble, owner_day, keypad):
        f()
    print('ok')
