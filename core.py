from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
import hashlib
import re
import shutil
import sqlite3
import subprocess
import tempfile
from difflib import SequenceMatcher
from contextlib import contextmanager

def normalize(text):
    return text.lower().replace('ё', 'е').replace(',', '.')

def numbers(text):
    # All dimensions are compared in millimetres; unlabelled values assume mm.
    found = []
    prepared = re.sub(r'(?<=\d)\s*[xх×]\s*(?=\d)', ' ', normalize(text))
    prepared = re.sub(r'(?<!\w)[rрø⌀ф]\s*(?=\d)', ' ', prepared)
    for match in re.finditer(r'(?<![\w.])\d+(?:[.,]\d+)?\s*(мм|см|mm|cm|м\b|m\b)?', prepared):
        value = float(re.search(r'\d+(?:\.\d+)?', match[0])[0])
        value *= {'см': 10, 'cm': 10, 'м': 1000, 'm': 1000}.get(match[1], 1)
        found.append(value)
    return found

def dimension_candidates(text):
    """Conservative suggestions, never a claim of geometric interpretation."""
    result = []
    for line in text.splitlines():
        line = line.strip()
        if re.search(r'scale|масштаб|fig|рис\.|гост|iso|дата|date|sheet|лист|taper|1\s*:', line, re.I):
            continue
        # OCR often confuses I/1 and O/0 in a numeric value directly before CRS/PCD.
        contextual = re.fullmatch(r'([0-9IOil.,]+)\s*(CRS|PCD)', line, re.I)
        if contextual:
            line = contextual[1].translate(str.maketrans({'I':'1','i':'1','l':'1','O':'0','o':'0'}))
        # Accept isolated measurements, dimension chains, and explicit radius/diameter.
        for match in re.finditer(r'(?<!\w)([RrРрØø⌀Фф]\s*\d+(?:[.,]\d+)?)', line):
            value = re.sub(r'\s+', '', match[1]).replace(',', '.')
            value = re.sub(r'^[Ррr]', 'R', value)
            value = re.sub(r'^[Øø⌀Фф]', 'Ø', value)
            if value not in result: result.append(value)
        clean = re.sub(r'\b(?:mm|мм|cm|см|CRS|PCD)\b', '', line, flags=re.I).strip()
        if re.fullmatch(r'\d+(?:[.,]\d+)?(?:\s*[xх×; ]\s*\d+(?:[.,]\d+)?)*', clean):
            for value in numbers(line):
                if 0 < value < 100000:
                    formatted = f'{value:g}'
                    if formatted not in result: result.append(formatted)
    return ' '.join(result)

def rank(query, rows):
    qnums = numbers(query)
    stop = {'найди', 'найти', 'чертеж', 'размер', 'размеры', 'мм', 'см', 'mm', 'cm', 'мне', 'нужен', 'нужна', 'по', 'с', 'и'}
    words = [w for w in re.findall(r'[a-zа-я]+', normalize(query)) if w not in stop]
    results = []
    for row in rows:
        content = normalize(row['title'] + ' ' + row['notes'] + ' ' + row['text'])
        tokens = re.findall(r'[a-zа-я]+', content)
        lexical = sum(max((SequenceMatcher(None, w, t).ratio() for t in tokens), default=0) for w in words) / max(1, len(words))
        # Prefer reviewed dimension fields over incidental numbers in a title block.
        values = numbers(row['dimensions'] or row['text'])
        gaps = [min((abs(v-n) / max(abs(n), 1) for v in values), default=1) for n in qnums]
        numeric = sum(max(0, 1-g*4) for g in gaps) / max(1, len(gaps))
        score = (0.8*numeric + 0.2*lexical) if qnums and words else numeric if qnums else lexical
        if score >= 0.25:
            reason = f'Близость размеров: {numeric:.0%}' if qnums else 'Совпадение описания'
            results.append((score, reason, row))
    return sorted(results, key=lambda x: (-x[0], x[2]['id']))[:2]

class Catalog:
    def __init__(self, root=ROOT / 'data'):
        self.root = Path(root)
        (self.root / 'files').mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS drawings (
                id INTEGER PRIMARY KEY, digest TEXT UNIQUE, title TEXT NOT NULL,
                filename TEXT NOT NULL, text TEXT DEFAULT '', notes TEXT DEFAULT '',
                dimensions TEXT DEFAULT '', status TEXT DEFAULT 'Требует проверки')''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(drawings)')}
            for name in ('auto_dimensions', 'ocr_text', 'ai_result'):
                if name not in columns:
                    db.execute(f"ALTER TABLE drawings ADD COLUMN {name} TEXT DEFAULT ''")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'catalog.sqlite3')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM drawings ORDER BY id DESC')]

    def import_file(self, source):
        source = Path(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with self.connect() as db:
            old = db.execute('SELECT id FROM drawings WHERE digest=?', (digest,)).fetchone()
            if old:
                return old[0], 'Этот файл уже в каталоге'
        dest = self.root / 'files' / (digest + source.suffix.lower())
        shutil.copy2(source, dest)
        try:
            text = extract(dest)
            status = 'Требует проверки' if text.strip() else 'Текст не найден — заполните вручную'
        except Exception as error:
            text = ''
            status = 'Ошибка распознавания: ' + str(error)[:350]
        with self.connect() as db:
            dimensions = dimension_candidates(text)
            cursor = db.execute('INSERT INTO drawings(digest,title,filename,text,status,dimensions,auto_dimensions,ocr_text) VALUES(?,?,?,?,?,?,?,?)',
                                (digest, source.stem, dest.name, text, status, dimensions, dimensions, text))
            return cursor.lastrowid, status

    def reprocess(self, item_id):
        row = next(r for r in self.rows() if r['id'] == item_id)
        text = extract(self.root / 'files' / row['filename'])
        dimensions = dimension_candidates(text)
        # Re-read after OCR: do not overwrite edits made while the worker ran.
        with self.connect() as db:
            current = dict(db.execute('SELECT * FROM drawings WHERE id=?', (item_id,)).fetchone())
            verified = current['status'] == 'Проверен технологом'
            editable = not verified and (not current['dimensions'] or current['dimensions'] == current['auto_dimensions'])
            new_text = text if not verified and (not current['text'] or current['text'] == current['ocr_text']) else current['text']
            # Legacy OCR text has no origin marker, so preserve it and expose the new OCR separately.
            db.execute('UPDATE drawings SET text=?,dimensions=?,auto_dimensions=?,ocr_text=? WHERE id=?',
                       (new_text, dimensions if editable else current['dimensions'], dimensions, text, item_id))
        return dimensions

    def save(self, item_id, title, dimensions, notes, text, confirmed):
        with self.connect() as db:
            db.execute('UPDATE drawings SET title=?,dimensions=?,notes=?,text=?,status=? WHERE id=?',
                       (title, dimensions, notes, text, 'Проверен технологом' if confirmed else 'Требует проверки', item_id))

    def save_analysis(self, item_id, result):
        import json
        with self.connect() as db:
            db.execute('UPDATE drawings SET ai_result=? WHERE id=?',
                       (json.dumps(result,ensure_ascii=False), item_id))

    def save_dimensions(self, item_id, dimensions):
        """Applying AI suggestions does not approve them or alter other fields."""
        with self.connect() as db:
            cursor = db.execute('UPDATE drawings SET dimensions=?,status=? WHERE id=?',
                                (dimensions, 'Требует проверки', item_id))
            if cursor.rowcount != 1:
                raise ValueError('Карточка больше не существует. Обновите каталог.')

def windows_ocr(image):
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((2400, 2400))
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'page.png'
        image.save(target)
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'ocr.ps1'), '-ImagePath', str(target)],
                                capture_output=True, encoding='utf-8', errors='replace', timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[-500:])
        return result.stdout.strip()

_engine = None

def ocr_image(image):
    """Read the complete sheet, enlarged overlapping tiles and vertical labels."""
    global _engine
    from PIL import ImageOps
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    if _engine is None:
        _engine = RapidOCR()
    image = ImageOps.exif_transpose(image).convert('RGB')
    image.thumbnail((3200, 3200))
    variants = [(image, True)]
    width, height = image.size
    for x in range(2):
        for y in range(2):
            tile = image.crop((max(0,x*width//2-50), max(0,y*height//2-50),
                               min(width,(x+1)*width//2+50), min(height,(y+1)*height//2+50)))
            tile = ImageOps.autocontrast(tile).resize((tile.width*2, tile.height*2))
            tile.thumbnail((2400,2400))
            variants.append((tile, False))
    variants.extend((image.rotate(angle, expand=True), True) for angle in (90,270))
    lines = []
    for variant, full_sheet in variants:
        result, _ = _engine(np.asarray(variant))
        for box, text, confidence in result or []:
            cx = sum(p[0] for p in box)/4/variant.width
            cy = sum(p[1] for p in box)/4/variant.height
            # Isolated numbers in the outer margin are commonly page numbers.
            if full_sheet and re.fullmatch(r'\d+', text) and (min(cx,cy)<0.07 or max(cx,cy)>0.93):
                continue
            if float(confidence) >= 0.60 and text not in lines:
                lines.append(text)
    # Retain Russian annotations through the OS language model where available.
    try:
        for line in windows_ocr(image).splitlines():
            if len(re.findall('[А-Яа-яЁё]', line)) >= 3 and not re.search(r'\d', line) and line not in lines:
                lines.append(line)
    except (RuntimeError, subprocess.TimeoutExpired):
        pass
    return '\n'.join(lines)

def extract(path):
    from PIL import Image, ImageSequence
    if path.suffix.lower() == '.pdf':
        import pymupdf
        pages = []
        with pymupdf.open(path) as document:
            for page in document:
                text = page.get_text().strip()
                # Scanned drawings may have only a page number in the text layer.
                if len(re.sub(r'\s', '', text)) < 30 or not dimension_candidates(text):
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                    text = text + '\n' + ocr_image(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))
                pages.append(text)
        return '\n\n'.join(pages)
    with Image.open(path) as image:
        return '\n\n'.join(ocr_image(frame.copy()) for frame in ImageSequence.Iterator(image))
