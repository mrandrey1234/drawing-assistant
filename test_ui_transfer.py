import json
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from unittest.mock import patch
from app import App
from core import Catalog

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = Catalog(Path(self.temp.name))
        result = {'parts':[
            {'name':'BODY','material':'','dimensions':[{'label':'Длина','kind':'linear','value':200,'unit':'mm'}]},
            {'name':'BUSH','material':'','dimensions':[{'label':'Радиус','kind':'radius','value':15,'unit':'mm'}]}
        ],'uncertain':[]}
        with self.catalog.connect() as db:
            self.item = db.execute('INSERT INTO drawings(digest,title,filename,dimensions,notes,text,status,ai_result) VALUES(?,?,?,?,?,?,?,?)',
                ('test','Подшипник','test.png','80','Сталь','Проверенный текст','Проверен технологом',json.dumps(result))).lastrowid
        with patch('app.Catalog',return_value=self.catalog):
            self.app = App()
        self.app.update()
        self.app.table.selection_set(str(self.item))
        self.app.update()

    def tearDown(self):
        for timer in self.app.tk.call('after','info'):
            self.app.after_cancel(timer)
        self.app.destroy()
        self.temp.cleanup()

    def transfer(self,part):
        self.app.show_analysis()
        self.app.update()
        dialog = next(w for w in self.app.winfo_children() if isinstance(w,tk.Toplevel))
        combo = next(w for w in descendants(dialog) if isinstance(w,ttk.Combobox))
        combo.current(part)
        button = next(w for w in descendants(dialog) if isinstance(w,ttk.Button))
        button.invoke()
        self.app.update()
        self.assertFalse(dialog.winfo_exists())

    def test_all_parts_saved_and_visible(self):
        self.transfer(0)
        row = self.catalog.rows()[0]
        self.assertEqual(row['dimensions'],'200 R15')
        self.assertEqual(row['status'],'Требует проверки')
        self.assertEqual((row['title'],row['notes'],row['text']),('Подшипник','Сталь','Проверенный текст'))
        self.assertEqual(self.app.dim_var.get(),'200 R15')
        self.assertEqual(self.app.table.item(str(self.item),'values')[1],'200 R15')
        self.app.refresh()
        self.app.table.selection_set(str(self.item))
        self.app.update()
        self.assertEqual(self.app.dim_var.get(),'200 R15')

    def test_one_part_saved(self):
        self.transfer(2)
        self.assertEqual(self.catalog.rows()[0]['dimensions'],'R15')

if __name__ == '__main__': unittest.main()
