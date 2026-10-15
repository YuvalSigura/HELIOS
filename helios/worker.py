"""Asynchronous CSV exporter with intentional cross-tenant confused-deputy behavior."""
import csv
import io
import os
import time
import uuid
import boto3
import redis
from helios.db import database,audit

BUCKET='helios-exports'

def s3_client():
    return boto3.client('s3',endpoint_url=os.environ['S3_ENDPOINT'],
                        aws_access_key_id=os.environ['S3_ACCESS'],
                        aws_secret_access_key=os.environ['S3_SECRET'],region_name='us-east-1')

def bucket_ready(client):
    for attempt in range(45):
        try:
            client.head_bucket(Bucket=BUCKET)
            return
        except Exception:
            try:
                client.create_bucket(Bucket=BUCKET)
                return
            except Exception:
                time.sleep(2)
    raise RuntimeError('Storage unavailable')

def process_export(job_id:str,client):
    with database() as conn:
        job=conn.execute("""SELECT e.*,r.connector_id,c.org_id AS source_org_id
          FROM exports e JOIN reports r ON r.id=e.report_id
          JOIN connectors c ON c.id=r.connector_id WHERE e.id=%s""",
          (uuid.UUID(job_id),)).fetchone()
        if not job or job['state']!='queued':
            return
        conn.execute("UPDATE exports SET state='running' WHERE id=%s",(job_id,))
    try:
        with database() as conn:
            # INTENTIONAL C: the worker uses connector owner authority; never rechecks tenant.
            rows=conn.execute("""SELECT period,department,amount,reference FROM data_rows
                                  WHERE connector_id=%s ORDER BY id""",
                                  (job['connector_id'],)).fetchall()
        out=io.StringIO()
        writer=csv.DictWriter(out,fieldnames=('period','department','amount','reference'))
        writer.writeheader()
        writer.writerows(rows)
        key=f"workspace/{job['requester_org_id']}/{job_id}.csv"
        client.put_object(Bucket=BUCKET,Key=key,Body=out.getvalue().encode(),
                          ContentType='text/csv')
        with database() as conn:
            conn.execute("UPDATE exports SET state='done',object_key=%s WHERE id=%s",(key,job_id))
            audit(conn,'export_completed',job['requested_by'],job['source_org_id'],
                  {'job_id':job_id,'source_org_id':job['source_org_id'],
                   'requester_org_id':job['requester_org_id'],'rows':len(rows)})
    except Exception as exc:
        with database() as conn:
            conn.execute("UPDATE exports SET state='failed' WHERE id=%s",(job_id,))
        print(f'Export failed {job_id}: {type(exc).__name__}: {exc}',flush=True)

def run():
    queue=redis.Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
    client=s3_client()
    bucket_ready(client)
    print('HELIOS worker ready',flush=True)
    while True:
        item=queue.brpop('helios:exports',timeout=5)
        if item:
            process_export(item[1],client)

if __name__=='__main__':
    run()
