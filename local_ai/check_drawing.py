import sys
import json
import time
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
from local_vision import analyze,dimension_text,describe

start=time.monotonic()
result=analyze(core.ROOT/'Примеры чертежей'/'01_Подшипник.png',progress=lambda s:print(s,flush=True))
output=core.ROOT/'local_ai'/'bearing_result.json'
output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(describe(result),flush=True)
print('DIMENSIONS:',dimension_text(result),flush=True)
print('ELAPSED:',round(time.monotonic()-start),flush=True)
