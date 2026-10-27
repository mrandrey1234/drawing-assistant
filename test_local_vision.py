import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import io
import json
import core
from local_vision import validate,dimension_text,image_payload,analyze,MODEL,ENDPOINT
from PIL import Image

def sample():
    return {'parts':[{'name':'Корпус','material':'','dimensions':[
        {'label':'Длина','kind':'linear','value':20,'unit':'cm'},
        {'label':'Скругление','kind':'radius','value':5,'unit':'mm'}]}], 'uncertain':['Мелкий текст не читается']}

class Tests(unittest.TestCase):
    def test_validate_units(self):
        self.assertEqual(dimension_text(validate(sample())),'200 R5')
        for bad in (float('nan'),float('inf'),-5,True,'20'):
            result=sample(); result['parts'][0]['dimensions'][0]['value']=bad
            with self.assertRaises(ValueError): validate(result)
        with self.assertRaises(ValueError): validate({})
        compact={'parts':[{'name':'Body','dimensions':[{'kind':'linear','value':200,'unit':'mm'}]}],'uncertain':[]}
        self.assertEqual(dimension_text(validate(compact)),'200')

    def test_page_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'image.png'
            Image.new('RGB',(50,50),'white').save(path)
            self.assertTrue(image_payload(path))
            with self.assertRaises(ValueError): image_payload(path,2)

    def test_loopback_stream(self):
        calls=[]
        def fake_request(route,payload=None,timeout=10):
            calls.append((route,payload))
            if route == '/api/tags': return io.BytesIO(json.dumps({'models':[{'name':MODEL}]}).encode())
            response={'message':{'content':json.dumps(sample())},'done':True}
            return io.BytesIO((json.dumps(response)+'\n').encode())
        with patch('local_vision.ensure_server'),patch('local_vision.image_payload',return_value='image'),patch('local_vision.request',side_effect=fake_request):
            result=analyze('dummy.png')
        self.assertEqual(result['model'],MODEL)
        self.assertEqual(ENDPOINT,'http://127.0.0.1:11435')
        self.assertNotIn('cloud',calls[1][1]['model'])
        self.assertEqual(calls[1][1]['keep_alive'],0)

    def test_analysis_does_not_change_verified_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'sample.png'
            Image.new('RGB',(20,20),'white').save(source)
            catalog=core.Catalog(Path(folder)/'catalog')
            with patch('core.extract',return_value='200'):
                item,_=catalog.import_file(source)
            catalog.save(item,'Корпус','200','Сталь','Текст',True)
            before=catalog.rows()[0]
            catalog.save_analysis(item,sample())
            after=catalog.rows()[0]
            for key in before:
                if key!='ai_result': self.assertEqual(before[key],after[key])

if __name__=='__main__': unittest.main()
