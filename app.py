import os
import threading
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core import Catalog, ROOT, rank

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Чертежи • помощник технолога')
        self.geometry('1180x780')
        self.minsize(900, 620)
        self.catalog = Catalog()
        self.current = None
        self.busy = False
        self.events = __import__('queue').Queue()
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton', padding=8)
        style.configure('Treeview', rowheight=34)
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Библиотека чертежей', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Загрузите → проверьте распознавание → найдите нужный чертёж', padding=(0, 8)).pack(anchor='w')
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', pady=10)
        self.upload = ttk.Button(toolbar, text='+ Загрузить чертежи', command=self.load)
        self.upload.pack(side='left')
        self.query = ttk.Entry(toolbar, font=('Segoe UI', 12))
        self.query.pack(side='left', fill='x', expand=True, padx=12)
        self.query.bind('<Return>', lambda e: self.search())
        ttk.Button(toolbar, text='Найти', command=self.search).pack(side='left')
        ttk.Button(toolbar, text='Все', command=self.refresh).pack(side='left', padx=(8, 0))
        ttk.Label(frame, text='Например: фланец 120 80 10 • вал диаметр 25 • корпус сталь').pack(anchor='w')
        self.status = tk.StringVar(value='Каталог готов. Поиск показывает до двух ближайших вариантов.')
        ttk.Label(frame, textvariable=self.status, wraplength=1050).pack(anchor='w', pady=10)
        self.table = ttk.Treeview(frame, columns=('title', 'dimensions', 'status', 'match'), show='headings', height=7)
        for key, title, width in [('title','Название',260), ('dimensions','Размеры, мм',180), ('status','Проверка',270), ('match','Соответствие запросу',230)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width)
        self.table.pack(fill='both', expand=True)
        self.table.bind('<<TreeviewSelect>>', self.select)
        self.table.bind('<Double-1>', lambda e: self.open_file())
        form = ttk.LabelFrame(frame, text='Карточка чертежа · проверьте результат распознавания', padding=12)
        form.pack(fill='both', expand=True, pady=(16, 0))
        self.title_var, self.dim_var, self.note_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (label, var) in enumerate([('Название', self.title_var), ('Размеры (мм, либо укажите см/м)', self.dim_var), ('Описание, материал, обозначение', self.note_var)]):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=3)
            entry = ttk.Entry(form, textvariable=var)
            entry.grid(row=i, column=1, sticky='ew', padx=(12, 0))
            if var is self.dim_var:
                self.dim_entry = entry
        form.columnconfigure(1, weight=1)
        self.text = tk.Text(form, height=6, wrap='word', font=('Segoe UI', 10))
        self.text.grid(row=3, column=0, columnspan=2, sticky='nsew', pady=8)
        scroll = ttk.Scrollbar(form, orient='vertical', command=self.text.yview)
        scroll.grid(row=3, column=2, sticky='ns', pady=8)
        self.text.configure(yscrollcommand=scroll.set)
        form.rowconfigure(3, weight=1)
        self.ocr_info = tk.StringVar(value='')
        ttk.Label(form, textvariable=self.ocr_info, wraplength=1000).grid(row=4, column=0, columnspan=2, sticky='w', pady=4)
        recognition = ttk.Frame(form)
        recognition.grid(row=5, column=0, columnspan=2, sticky='ew', pady=4)
        self.retry = ttk.Button(recognition, text='Распознать повторно', command=self.reprocess)
        self.retry.pack(side='left')
        ttk.Button(recognition, text='Взять данные из OCR', command=self.apply_ocr).pack(side='left', padx=8)
        ai_controls = ttk.Frame(form)
        ai_controls.grid(row=6, column=0, columnspan=2, sticky='ew', pady=4)
        self.ai_button = ttk.Button(ai_controls, text='Локальный ИИ · эксперимент', command=self.analyze_local)
        self.ai_button.pack(side='left')
        ttk.Label(ai_controls,text='Лист:').pack(side='left',padx=(10,3))
        self.page_var = tk.StringVar(value='1')
        ttk.Spinbox(ai_controls,from_=1,to=999,textvariable=self.page_var,width=5).pack(side='left')
        ttk.Button(ai_controls,text='Результат ИИ',command=self.show_analysis).pack(side='left',padx=8)
        actions = ttk.Frame(form)
        actions.grid(row=7, column=0, columnspan=2, sticky='ew')
        self.confirmed = tk.BooleanVar()
        ttk.Checkbutton(actions, text='Результат проверен технологом', variable=self.confirmed).pack(side='left')
        ttk.Button(actions, text='Сохранить карточку', command=self.save).pack(side='right')
        ttk.Button(actions, text='Открыть оригинал', command=self.open_file).pack(side='right', padx=8)
        self.refresh()
        self.after(200, self.poll)

    def populate(self, rows, matches=None):
        self.table.delete(*self.table.get_children())
        self.current = None
        self.title_var.set(''); self.dim_var.set(''); self.note_var.set('')
        self.text.delete('1.0', 'end'); self.confirmed.set(False)
        self.ocr_info.set('')
        for row in rows:
            self.table.insert('', 'end', iid=str(row['id']), values=(row['title'], row['dimensions'], row['status'], (matches or {}).get(row['id'], '')))

    def refresh(self):
        rows = self.catalog.rows()
        self.populate(rows)
        self.status.set(f'В каталоге: {len(rows)}. Введите размеры или описание для поиска.')

    def search(self):
        query = self.query.get().strip()
        if not query:
            self.refresh(); return
        results = rank(query, self.catalog.rows())
        self.populate([r for _, _, r in results], {r['id']: f'{s:.0%} · {why}' for s, why, r in results})
        self.status.set('Ближайшие варианты. Процент — оценка сходства, а не вероятность правильного ответа.' if results else 'Подходящие чертежи не найдены. Уточните запрос или заполните размеры в карточках.')

    def select(self, event=None):
        selection = self.table.selection()
        if not selection: return
        self.current = next(r for r in self.catalog.rows() if r['id'] == int(selection[0]))
        row = self.current
        self.title_var.set(row['title']); self.dim_var.set(row['dimensions']); self.note_var.set(row['notes'])
        self.text.delete('1.0', 'end'); self.text.insert('1.0', row['text'])
        self.confirmed.set(row['status'] == 'Проверен технологом')
        self.ocr_info.set('OCR предлагает: ' + (row.get('auto_dimensions') or 'размеры пока не найдены') + '. Сверьте с оригиналом; возможны ошибки и пропуски.')

    def apply_ocr(self):
        if not self.current or self.busy: return
        if not self.current.get('ocr_text'):
            self.status.set('Сначала выполните повторное распознавание.'); return
        self.dim_var.set(self.current.get('auto_dimensions', ''))
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.current['ocr_text'])
        self.confirmed.set(False)
        self.status.set('Данные OCR подставлены в карточку. Проверьте и нажмите «Сохранить карточку».')

    def analyze_local(self):
        if not self.current or self.busy: return
        if not self.title_var.get().strip():
            messagebox.showwarning('Название','Укажите название чертежа.'); return
        try:
            page = int(self.page_var.get())
            if page < 1: raise ValueError()
        except ValueError:
            messagebox.showwarning('Лист','Введите номер листа от 1.'); return
        item_id = self.current['id']
        path = self.catalog.root/'files'/self.current['filename']
        self.save()
        self.busy = True
        for button in (self.upload,self.retry,self.ai_button): button.configure(state='disabled')
        self.status.set('Запуск локальной модели. Чертёж остаётся на компьютере…')
        def work():
            try:
                import core
                core._engine = None
                import gc
                gc.collect()
                from local_vision import analyze
                result = analyze(path,page,lambda value:self.events.put(('progress',value)))
                self.catalog.save_analysis(item_id,result)
                self.events.put(('analyzed',item_id))
            except Exception as error:
                self.events.put(('error',str(error)))
                self.events.put(('done','Анализ не выполнен. Размеры и описание сохранены без изменений.'))
        threading.Thread(target=work,daemon=True).start()

    def show_analysis(self):
        if not self.current: return
        if self.busy:
            self.status.set('Дождитесь завершения обработки, затем откройте результат ИИ.'); return
        if not self.current.get('ai_result'):
            self.status.set('Для этой карточки ещё нет результата ИИ. Нажмите «Анализ ИИ на компьютере».'); return
        from local_vision import describe, dimension_text, validate
        try: result = validate(json.loads(self.current['ai_result']))
        except (ValueError,TypeError) as error:
            messagebox.showerror('Результат ИИ',str(error)); return
        item_id = self.current['id']
        window = tk.Toplevel(self)
        window.title('Результат локального анализа — проверьте по оригиналу')
        window.geometry('800x620')
        window.transient(self)
        window.grab_set()
        output = tk.Text(window,wrap='word',font=('Segoe UI',11))
        output.pack(fill='both',expand=True,padx=12,pady=12)
        import re
        proposed = set(dimension_text(result).split())
        observed = set(re.findall(r'[RØ]?\d+(?:\.\d+)?',self.current.get('auto_dimensions','')))
        extra = sorted(proposed-observed)
        comparison = '\n\nЗначения, которых нет в результате OCR (это не подтверждение ошибки или правильности):\n' + (' '.join(extra) or 'Все предложенные значения также встречаются в OCR.')
        output.insert('1.0',describe(result)+comparison)
        output.configure(state='disabled')
        ttk.Label(window,text='Проверьте значения по оригиналу. Кнопка ниже заменит и сохранит поле «Размеры» выбранными значениями. Статус станет «Требует проверки».',wraplength=760).pack(anchor='w',padx=12)
        selection = ttk.Combobox(window,state='readonly',values=['Все детали']+[p['name'] or 'Без названия' for p in result['parts']])
        selection.current(0)
        selection.pack(fill='x',padx=12,pady=8)
        def apply():
            if self.busy or not self.current or self.current['id'] != item_id:
                messagebox.showinfo('Карточка','Сначала выберите исходную карточку и дождитесь завершения обработки.'); return
            index = selection.current()
            chosen = result if index == 0 else {'parts':[result['parts'][index-1]]}
            dimensions = dimension_text(chosen)
            if not dimensions:
                messagebox.showinfo('Размеры','Модель не предложила размеров для выбранной детали.'); return
            try:
                self.catalog.save_dimensions(item_id, dimensions)
            except Exception as error:
                messagebox.showerror('Не удалось сохранить размеры',str(error),parent=window)
                return
            self.dim_var.set(dimensions)
            self.confirmed.set(False)
            self.current['dimensions'] = dimensions
            self.current['status'] = 'Требует проверки'
            values = list(self.table.item(str(item_id),'values'))
            values[1] = dimensions
            values[2] = 'Требует проверки'
            values[3] = ''  # Any old search score was computed before this edit.
            self.table.item(str(item_id),values=values)
            self.status.set(f'Размеры сохранены в карточке «{self.current["title"]}»: {dimensions}. Проверьте их по оригиналу.')
            self.ocr_info.set(f'Сохранено из ИИ: {dimensions}. Требуется проверка технологом.')
            window.destroy()
            self.lift()
            self.dim_entry.focus_set()
            self.dim_entry.selection_range(0,'end')
        ttk.Button(window,text='Применить и сохранить размеры',command=apply).pack(padx=12,pady=12)

    def reprocess(self):
        if not self.current or self.busy: return
        if not self.title_var.get().strip():
            messagebox.showwarning('Название', 'Укажите название чертежа.'); return
        item_id = self.current['id']
        # Save the visible draft before background recognition; preserve manual edits.
        self.save()
        self.busy = True
        self.upload.configure(state='disabled'); self.retry.configure(state='disabled')
        self.status.set('Повторное распознавание: чтение листа и увеличенных фрагментов…')
        def work():
            try:
                dimensions = self.catalog.reprocess(item_id)
                self.events.put(('reprocessed', (item_id, dimensions)))
            except Exception as error:
                self.events.put(('error', str(error)))
                self.events.put(('done', 'Не удалось распознать. Сохранённые данные не изменены.'))
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        if not self.current: return
        if not self.title_var.get().strip():
            messagebox.showwarning('Название', 'Укажите название чертежа.'); return
        self.catalog.save(self.current['id'], self.title_var.get().strip(), self.dim_var.get(), self.note_var.get(), self.text.get('1.0', 'end-1c'), self.confirmed.get())
        self.refresh()
        self.status.set('Карточка сохранена. Изменения уже учитываются при поиске.')

    def open_file(self):
        if self.current:
            try: os.startfile(self.catalog.root / 'files' / self.current['filename'])
            except OSError as e: messagebox.showerror('Не удалось открыть', str(e))

    def load(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(title='Выберите чертежи', filetypes=[('Чертежи PDF и изображения', '*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp')])
        if not paths: return
        self.busy = True
        self.upload.configure(state='disabled')
        self.retry.configure(state='disabled')
        def work():
            for i, path in enumerate(paths, 1):
                self.events.put(('progress', f'Распознавание {i}/{len(paths)}: {os.path.basename(path)}'))
                try:
                    _, status = self.catalog.import_file(path)
                    self.events.put(('progress', status))
                except Exception as e:
                    self.events.put(('error', f'{os.path.basename(path)}: {e}'))
            self.events.put(('done', 'Загрузка завершена. Выберите чертёж и проверьте распознанные данные.'))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind in ('done', 'reprocessed', 'analyzed'):
                self.busy = False
                self.upload.configure(state='normal'); self.retry.configure(state='normal'); self.ai_button.configure(state='normal'); self.refresh()
            if kind == 'analyzed':
                self.table.selection_set(str(value)); self.table.see(str(value)); self.select()
                self.status.set('Локальный анализ завершён. Предложения ИИ требуют проверки по чертежу.')
                self.show_analysis()
                continue
            if kind == 'reprocessed':
                item_id, dimensions = value
                self.table.selection_set(str(item_id)); self.table.see(str(item_id)); self.select()
                self.status.set('Распознавание завершено. ' + ('Найденные размеры показаны в карточке. Кнопка «Взять данные из OCR» подставит новый текст и размеры.' if dimensions else 'Размеры не найдены. Можно заполнить вручную.'))
                continue
            if kind == 'error': messagebox.showerror('Ошибка загрузки', value)
            self.status.set(value)
        self.after(200, self.poll)

if __name__ == '__main__':
    App().mainloop()
