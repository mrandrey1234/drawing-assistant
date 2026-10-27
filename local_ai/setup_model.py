"""Run once after the portable runtime has been unpacked. Downloads model only."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_vision import ensure_server, request, MODEL
import json
ensure_server()
with request('/api/pull', {'model':MODEL, 'stream':True}, timeout=1200) as response:
    last = None
    for line in response:
        item = json.loads(line)
        if item.get('error'): raise RuntimeError(item['error'])
        percent = int(100*item.get('completed',0)/max(item.get('total',1),1))
        state = (item.get('status'),percent//10)
        if state != last:
            print(item.get('status'), str(percent)+'%',flush=True)
            last = state
