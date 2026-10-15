"""HELIOS vulnerable customer-facing SaaS: use on loopback only."""
import os
import uuid
from pathlib import Path
import boto3
import redis
from botocore.exceptions import ClientError
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from helios.db import database, password_valid, audit

BASE=Path(__file__).parent
app=FastAPI(title='Helios Workspace',docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
templates=Jinja2Templates(directory=str(BASE/'templates'))
signer=URLSafeTimedSerializer(os.environ['SESSION_SECRET'],salt='helios-session')

def current_user(request:Request):
    token=request.cookies.get('helios_session')
    if not token:
        raise HTTPException(401,'Login required')
    try:
        uid=signer.loads(token,max_age=28800)
    except (BadSignature,SignatureExpired):
        raise HTTPException(401,'Session expired')
    with database() as conn:
        user=conn.execute('SELECT id,org_id,email,role FROM users WHERE id=%s',(uid,)).fetchone()
    if not user:
        raise HTTPException(401,'Invalid session')
    return user

def visible_report(conn,report_id,user):
    report=conn.execute("""SELECT r.*,o.name AS org_name FROM reports r
                JOIN organizations o ON o.id=r.owner_org_id WHERE r.id=%s""",(report_id,)).fetchone()
    if not report:
        raise HTTPException(404,'Report not found')
    if report['owner_org_id']!=user['org_id']:
        share=conn.execute('SELECT 1 FROM report_shares WHERE report_id=%s AND grantee_org_id=%s',
                           (report_id,user['org_id'])).fetchone()
        if not share:
            raise HTTPException(404,'Report not found')
    return report

def s3():
    return boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT'],
                        aws_access_key_id=os.environ['S3_ACCESS'],
                        aws_secret_access_key=os.environ['S3_SECRET'],region_name='us-east-1')

@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    return templates.TemplateResponse('index.html',{'request':request})

@app.get('/lab-health')
def health():
    with database() as conn:
        conn.execute('SELECT 1').fetchone()
    return {'status':'ok','service':'helios-workspace'}

@app.post('/api/session')
async def login(request:Request,response:Response):
    body=await request.json()
    if not isinstance(body,dict):
        raise HTTPException(400,'Invalid request')
    with database() as conn:
        user=conn.execute('SELECT * FROM users WHERE email=%s',(str(body.get('email','')),)).fetchone()
    if not user or not password_valid(str(body.get('password','')),user['pass_hash']):
        raise HTTPException(401,'Invalid email or password')
    response.set_cookie('helios_session',signer.dumps(user['id']),max_age=28800,
                        httponly=True,samesite='strict',secure=False)
    return {'email':user['email'],'role':user['role']}

@app.delete('/api/session')
def logout(response:Response):
    response.delete_cookie('helios_session',samesite='strict')
    return {'ok':True}

@app.get('/api/me')
def me(user=Depends(current_user)):
    with database() as conn:
        org=conn.execute('SELECT name FROM organizations WHERE id=%s',(user['org_id'],)).fetchone()
    return {'email':user['email'],'role':user['role'],'organization':org['name'],'org_id':user['org_id']}

@app.get('/api/reports')
def reports(user=Depends(current_user)):
    with database() as conn:
        return conn.execute("""SELECT r.id,r.title,r.summary,r.owner_org_id,
                      o.name AS organization,(r.owner_org_id<>%s) AS shared
                      FROM reports r JOIN organizations o ON o.id=r.owner_org_id
                      WHERE r.owner_org_id=%s OR EXISTS
                       (SELECT 1 FROM report_shares s WHERE s.report_id=r.id
                        AND s.grantee_org_id=%s)
                      ORDER BY r.id""",
                      (user['org_id'],user['org_id'],user['org_id'])).fetchall()

@app.get('/api/reports/{report_id}')
def detail(report_id:int,user=Depends(current_user)):
    with database() as conn:
        report=visible_report(conn,report_id,user)
        return {k:report[k] for k in ('id','title','summary','owner_org_id','org_name','cloned_from')}

@app.get('/api/reports/{report_id}/notes')
def notes(report_id:int,user=Depends(current_user)):
    with database() as conn:
        report=visible_report(conn,report_id,user)
        # INTENTIONAL A: a share authorizes the report, not its internal-only notes.
        items=conn.execute('SELECT id,visibility,body FROM report_notes WHERE report_id=%s ORDER BY id',
                           (report_id,)).fetchall()
        audit(conn,'notes_read',user['id'],report['owner_org_id'],
              {'report_id':report_id,'reader_org_id':user['org_id'],
               'internal_ids':[n['id'] for n in items if n['visibility']=='internal']})
        return items

@app.post('/api/reports/{report_id}/clone')
def clone(report_id:int,user=Depends(current_user)):
    with database() as conn:
        report=visible_report(conn,report_id,user)
        # INTENTIONAL B: source connector trust binding copied into another tenant.
        copy=conn.execute("""INSERT INTO reports(owner_org_id,title,summary,connector_id,cloned_from)
                             VALUES(%s,%s,%s,%s,%s) RETURNING id""",
                          (user['org_id'],'Copy of '+report['title'],report['summary'],
                           report['connector_id'],report['id'])).fetchone()
        audit(conn,'report_cloned',user['id'],report['owner_org_id'],
              {'new_report_id':copy['id'],'source_report_id':report_id,
               'requester_org_id':user['org_id']})
    return {'id':copy['id'],'status':'created'}

@app.post('/api/reports/{report_id}/exports',status_code=202)
def request_export(report_id:int,user=Depends(current_user)):
    job=str(uuid.uuid4())
    with database() as conn:
        report=visible_report(conn,report_id,user)
        if report['owner_org_id']!=user['org_id']:
            raise HTTPException(403,'Clone partner reports before exporting')
        conn.execute("""INSERT INTO exports(id,requested_by,requester_org_id,report_id,state)
                        VALUES(%s,%s,%s,%s,'queued')""",
                     (job,user['id'],user['org_id'],report_id))
        audit(conn,'export_queued',user['id'],user['org_id'],
              {'job_id':job,'report_id':report_id})
    try:
        redis.Redis.from_url(os.environ['REDIS_URL']).lpush('helios:exports',job)
    except redis.RedisError:
        with database() as conn:
            conn.execute("UPDATE exports SET state='failed' WHERE id=%s",(job,))
        raise HTTPException(503,'Export queue unavailable')
    return {'job_id':job,'state':'queued'}

@app.get('/api/exports/{job_id}')
def export_status(job_id:uuid.UUID,user=Depends(current_user)):
    with database() as conn:
        job=conn.execute('SELECT id,report_id,state FROM exports WHERE id=%s AND requester_org_id=%s',
                         (job_id,user['org_id'])).fetchone()
    if not job:
        raise HTTPException(404,'Export not found')
    return {'job_id':str(job['id']),'report_id':job['report_id'],'state':job['state'],
            'download_url':f'/api/exports/{job_id}/download' if job['state']=='done' else None}

@app.get('/api/exports/{job_id}/download')
def download(job_id:uuid.UUID,user=Depends(current_user)):
    with database() as conn:
        job=conn.execute("""SELECT * FROM exports WHERE id=%s AND requester_org_id=%s
                            AND state='done'""",(job_id,user['org_id'])).fetchone()
        if not job:
            raise HTTPException(404,'Export not available')
        audit(conn,'export_downloaded',user['id'],user['org_id'],
              {'job_id':str(job_id)})
    try:
        response=s3().get_object(Bucket='helios-exports',Key=job['object_key'])
    except ClientError:
        raise HTTPException(503,'Export temporarily unavailable')
    return StreamingResponse(response['Body'].iter_chunks(chunk_size=65536),
                             media_type='text/csv',
                             headers={'Content-Disposition':f'attachment; filename="export-{job_id}.csv"',
                                      'Cache-Control':'no-store'})
