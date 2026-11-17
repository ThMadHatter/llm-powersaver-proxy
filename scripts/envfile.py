from pathlib import Path

def load(path):
    values={}
    p=Path(path)
    if p.exists():
        for raw in p.read_text().splitlines():
            line=raw.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); values[k.strip()]=v.strip().strip('"').strip("'")
    return values

def update(path, changes):
    p=Path(path); lines=p.read_text().splitlines() if p.exists() else []
    done=set(); out=[]
    for line in lines:
        if '=' in line and not line.lstrip().startswith('#'):
            k=line.split('=',1)[0].strip()
            if k in changes: out.append(f'{k}={changes[k]}'); done.add(k); continue
        out.append(line)
    if out and out[-1] != '': out.append('')
    if any(k not in done for k in changes): out.append('# Workstation Power Agent / diagnostics')
    out.extend(f'{k}={v}' for k,v in changes.items() if k not in done)
    p.write_text('\n'.join(out)+'\n')
