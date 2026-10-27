from core import ROOT
from PIL import Image, ImageOps, ImageFilter
import subprocess, tempfile, json

with tempfile.TemporaryDirectory() as folder:
    from pathlib import Path
    image = Image.open(ROOT/'Примеры чертежей'/'01_Подшипник.png').convert('RGB')
    variants = {'original':image}
    for angle in (0,90,270):
        rotated = image.rotate(angle, expand=True)
        w,h=rotated.size
        for x in range(3):
            for y in range(2):
                crop=rotated.crop((max(0,x*w//3-60),max(0,y*h//2-60),min(w,(x+1)*w//3+60),min(h,(y+1)*h//2+60)))
                crop=ImageOps.autocontrast(crop.convert('L')).resize((crop.width*2,crop.height*2))
                crop.thumbnail((2400,2400))
                variants[f'{angle}_{x}_{y}']=crop
    for name,im in variants.items(): im.save(Path(folder)/(name+'.png'))
    r=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'ocr.ps1'),'-ImagePath',folder],capture_output=True,encoding='utf-8',errors='replace')
    (ROOT/'ocr_probe.json').write_text(r.stdout,encoding='utf-8')
    print(r.stdout or r.stderr)
