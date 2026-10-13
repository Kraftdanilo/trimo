import subprocess, time, urllib.request, json, sys

proc = subprocess.Popen(
    ['c:/Users/HP/Documents/carton-studio/.venv/Scripts/python.exe',
     '-c', 'import uvicorn; uvicorn.run("server:app", host="127.0.0.1", port=8123)'],
    cwd='c:/Users/HP/Documents/carton-studio',
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
)

base = 'http://127.0.0.1:8123'
ready = False
for _ in range(30):
    time.sleep(1)
    try:
        with urllib.request.urlopen(base + '/', timeout=3) as r:
            r.read()
        ready = True
        break
    except Exception:
        if proc.poll() is not None:
            break

if not ready:
    print('SERVER DID NOT START. Output:')
    try:
        print(proc.stdout.read())
    except Exception:
        pass
    proc.terminate()
    sys.exit(1)
print('server ready\n')

def get(url, t=8):
    with urllib.request.urlopen(url, timeout=t) as r:
        return r.status, r.read()

ok = True
try:
    for path, marker in [('/static/app.js', 'renderOverview'),
                         ('/static/style.css', '.ov-layout'),
                         ('/', 'panelOverview')]:
        s, body = get(base + path)
        present = marker in body.decode('utf-8', 'replace')
        print(f'{path}: status={s} contains {marker!r} = {present}')
        if not (s == 200 and present):
            ok = False

    s, body = get(base + '/api/projects')
    projects = json.loads(body)
    if projects:
        pid = projects[0]['id']
        s, body = get(f'{base}/api/projects/{pid}')
        script = json.loads(body)['script']
        n = len(script.get('scenes', []))
        s, body = get(f'{base}/api/projects/{pid}/scenes/0/code')
        code = json.loads(body)
        print(f'\nProjet {pid}: {n} scènes')
        print(f'scene 0 code keys: {sorted(code.keys())}')
        print(f'scene 0 html length: {len(code.get("html", ""))}')
        if not all(k in code for k in ('html', 'css', 'js')):
            ok = False
            print('ERREUR: clés html/css/js manquantes')
    else:
        print('Aucun projet existant')
except Exception as e:
    ok = False
    print('error:', repr(e))

proc.terminate()
print('\nRESULT:', 'ALL OK' if ok else 'FAILURES')
sys.exit(0 if ok else 1)

