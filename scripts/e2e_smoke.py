"""Real Web/API -> worker -> object storage -> independent oracle E2E test."""
import http.cookiejar
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE='http://127.0.0.1:18080'
CLIENT=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def request(path,method='GET',body=None,expect=200):
    payload=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(BASE+path,data=payload,method=method,
             headers={'Content-Type':'application/json'} if payload is not None else {})
    try:
        with CLIENT.open(req,timeout=10) as resp:
            status=resp.status
            data=resp.read()
    except urllib.error.HTTPError as exc:
        status=exc.code
        data=exc.read()
    if status!=expect:
        raise AssertionError(f'{method} {path}: expected {expect}, got {status}: {data[:200]!r}')
    if status in (401,403,404):
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return data

def oracle():
    result=subprocess.run(['docker','compose','--profile','operator','run','--rm','oracle'],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=100)
    if result.returncode not in (0,1):
        raise AssertionError('Oracle error: '+result.stderr[-2000:])
    return json.loads(result.stdout[result.stdout.find('{'):])

def main():
    for i in range(80):
        try:
            if request('/lab-health')['status']=='ok':
                break
        except Exception:
            time.sleep(2)
    else:
        raise AssertionError('Lab not healthy')
    before=oracle()
    assert before['user']=='NOT_YET' and before['root']=='NOT_YET',before
    env=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if '=' in line)
    request('/api/session','POST',{'email':'analyst@finch.test',
                                  'password':env['HELIOS_ANALYST_PASSWORD']})
    assert request('/api/me')['organization']=='Finch Labs'
    reports=request('/api/reports')
    assert any(r['id']==2 and r['shared'] for r in reports)
    assert not any(r['id']==3 for r in reports)
    request('/api/reports/3',expect=404)
    request('/api/reports/2/exports','POST',expect=403)
    note=request('/api/reports/2/notes')
    assert any(x['visibility']=='internal' for x in note)
    middle=oracle()
    assert middle['user']=='PASS' and middle['root']=='NOT_YET',middle
    copy=request('/api/reports/2/clone','POST')
    export=request(f"/api/reports/{copy['id']}/exports",'POST',expect=202)
    for i in range(45):
        state=request(f"/api/exports/{export['job_id']}")
        if state['state']=='done':
            break
        if state['state']=='failed':
            raise AssertionError('Export job failed')
        time.sleep(2)
    else:
        raise AssertionError('Export timed out')
    csv=request(state['download_url'])
    assert isinstance(csv,bytes) and b'2026-' in csv
    after=oracle()
    assert after['user']=='PASS' and after['root']=='PASS',after
    print(json.dumps({'result':'PASS','before':before,'after':after},indent=2))

if __name__=='__main__':
    main()
