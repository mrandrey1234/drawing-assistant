from pathlib import Path
import zipfile
root=Path(__file__).resolve().parent
target=root/'runtime'
target.mkdir(exist_ok=True)
with zipfile.ZipFile(root/'ollama-windows-amd64.zip') as archive:
    files=[]
    for info in archive.infolist():
        name=info.filename.replace('\\','/')
        # CPU runtime only: this computer has an integrated GPU and limited RAM.
        if any(word in name.lower() for word in ('cuda','rocm','vulkan')):
            continue
        resolved=(target/name).resolve()
        if not resolved.is_relative_to(target.resolve()):
            raise ValueError('Unsafe archive path')
        archive.extract(info,target)
        files.append(name)
    print('Extracted',len(files),'CPU runtime files',flush=True)
    print('\n'.join(files[:30]),flush=True)
