# make-shots.js가 찍은 화면을 잘라 줄여 ../images 에 넣는다. 사용: python3 prepare-images.py <make-shots 출력 폴더>
import os, sys
from PIL import Image

SRC = sys.argv[1]
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')


def save(src, dst, crop=None, width=None, jpeg=False):
    im = Image.open(os.path.join(SRC, src)).convert('RGB')
    if crop:
        im = im.crop(crop)
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    if jpeg:
        im.save(os.path.join(D, dst), quality=82, optimize=True)
    else:
        im.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(os.path.join(D, dst), optimize=True)


for n in (1, 2, 3):
    save(f'tv-screen{n}.png', f'tv-screen{n}.jpg', width=1280, jpeg=True)
save('admin-preview.png', 'admin-preview.jpg', jpeg=True)
save('admin-first-setup.png', 'admin-first-setup.png', crop=(0, 0, 1366, 260))
save('admin-top.png', 'admin-top.png')
for n in ['admin-calls', 'admin-soldout', 'admin-sections', 'admin-item-row', 'admin-item-new', 'admin-screens', 'admin-pos', 'devices-list', 'devices-usb']:
    save(n + '.png', n + '.png', width=1100)
save('reset.png', 'reset.png', crop=(0, 0, 680, 630))
save('phone-top.png', 'phone-top.jpg', width=780, jpeg=True)
print('ok')
