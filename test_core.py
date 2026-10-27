import tempfile
import unittest
from pathlib import Path
from core import Catalog, numbers, rank, extract, dimension_candidates, ROOT
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont

class Tests(unittest.TestCase):
    def test_dimension_candidates(self):
        self.assertEqual(dimension_candidates('SCALE 1:1\nFIG2\nГОСТ 1234\n80\nR20\nØ25\nI5OCRS\n200\n80'), '80 R20 Ø25 150 200')
        self.assertEqual(numbers('R20 Ø25 120x80'), [20,25,120,80])

    def test_reprocess_preserves_manual_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'test.png'
            Image.new('RGB',(20,20),'white').save(source)
            catalog = Catalog(Path(temp)/'catalog')
            with patch('core.extract', return_value='80\n200'):
                item,_ = catalog.import_file(source)
            self.assertEqual(catalog.rows()[0]['dimensions'], '80 200')
            catalog.save(item,'Правка','123','Материал','Исправленный текст',True)
            with patch('core.extract', return_value='90\n210'):
                catalog.reprocess(item)
            row = catalog.rows()[0]
            self.assertEqual((row['dimensions'],row['notes'],row['text'],row['status']), ('123','Материал','Исправленный текст','Проверен технологом'))
            self.assertEqual(row['auto_dimensions'], '90 210')
            with patch('core.extract', side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError): catalog.reprocess(item)
            self.assertEqual(catalog.rows()[0], row)

    @unittest.skipUnless((ROOT/'Примеры чертежей'/'01_Подшипник.png').exists(), 'Учебный чертёж не включён в репозиторий')
    def test_bearing_sample(self):
        text = extract(ROOT/'Примеры чертежей'/'01_Подшипник.png')
        dims = dimension_candidates(text)
        for value in (200,80,60): self.assertIn(value,numbers(dims))
        with tempfile.TemporaryDirectory() as temp:
            catalog = Catalog(Path(temp)/'catalog')
            with patch('core.extract', return_value=text):
                catalog.import_file(ROOT/'Примеры чертежей'/'01_Подшипник.png')
            self.assertEqual(rank('подшипник 200 60',catalog.rows())[0][2]['title'],'01_Подшипник')
    def test_units_and_ranking(self):
        self.assertEqual(numbers('12 см 25,5 мм'), [120, 25.5])
        rows = [dict(id=i, title='Фланец', notes='', text='', dimensions=d) for i, d in enumerate(['120 80 10','125 80 10','400 300 50'])]
        self.assertEqual([r['id'] for _, _, r in rank('фланец 120 80 10', rows)], [0, 1])
        self.assertEqual(rank('9000', rows), [])

    def test_pdf_storage_duplicate_and_edit(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'flange.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_text((70, 70), 'FLANGE 120 80 10')
                doc.save(path)
            catalog = Catalog(Path(temp) / 'db')
            item, _ = catalog.import_file(path)
            self.assertIn('120', catalog.rows()[0]['text'])
            self.assertEqual(catalog.import_file(path)[0], item)
            self.assertEqual(len(catalog.rows()), 1)
            catalog.save(item, 'Фланец', '120 80 10', 'Сталь', 'text', True)
            self.assertEqual(Catalog(Path(temp) / 'db').rows()[0]['status'], 'Проверен технологом')

    def test_real_windows_ocr(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'drawing.png'
            image = Image.new('RGB', (1400, 600), 'white')
            ImageDraw.Draw(image).text((60, 70), 'FLANGE 120 80 10', font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 60), fill='black')
            image.save(path)
            self.assertIn('120', extract(path))

if __name__ == '__main__': unittest.main()
