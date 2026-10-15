"""Seed a realistic multi-tenant business dataset and fresh secret markers."""
import os
import secrets
from pathlib import Path
from helios.db import database, password_hash

def seed():
    schema=Path(__file__).with_name('schema.sql').read_text(encoding='utf-8')
    with database() as conn:
        conn.execute(schema)
        if conn.execute('SELECT count(*) AS n FROM organizations').fetchone()['n']:
            print('Seed exists; preserving flags')
            return
        for row in [(1,'finch','Finch Labs'),(2,'aster','AsterPay'),(3,'cedar','CedarCloud')]:
            conn.execute('INSERT INTO organizations VALUES(%s,%s,%s)',row)
        for org_id,email,role,password in [
            (1,'analyst@finch.test','analyst',os.environ['LAB_ANALYST_PASSWORD']),
            (1,'manager@finch.test','manager',secrets.token_urlsafe(24)),
            (2,'reviewer@aster.test','reviewer',secrets.token_urlsafe(24)),
            (3,'analyst@cedar.test','analyst',secrets.token_urlsafe(24))
        ]:
            conn.execute('INSERT INTO users(org_id,email,role,pass_hash) VALUES(%s,%s,%s,%s)',
                         (org_id,email,role,password_hash(password)))
        for row in [(1,1,'Finch Operations'),(2,2,'AsterPay Settlement Ledger'),(3,3,'CedarCloud Utilization')]:
            conn.execute('INSERT INTO connectors(id,org_id,name) VALUES(%s,%s,%s)',row)
        user_flag='HELIOS{user_'+secrets.token_hex(15)+'}'
        root_flag='HELIOS{root_'+secrets.token_hex(15)+'}'
        conn.execute('INSERT INTO oracle_markers(kind,value) VALUES(%s,%s),(%s,%s)',('user',user_flag,'root',root_flag))
        conn.execute("INSERT INTO reports(owner_org_id,title,summary,connector_id) VALUES(1,'Finch Quarterly Pipeline','Quarterly sales operations overview',1)")
        conn.execute("INSERT INTO reports(owner_org_id,title,summary,connector_id) VALUES(2,'AsterPay Partner Settlement Summary','Shared partner settlement totals for Q3',2)")
        conn.execute("INSERT INTO reports(owner_org_id,title,summary,connector_id) VALUES(3,'CedarCloud Usage Summary','Internal consumption report',3)")
        for i in range(4,43):
            owner=1 if i%3==0 else (2 if i%3==1 else 3)
            conn.execute('INSERT INTO reports(owner_org_id,title,summary,connector_id) VALUES(%s,%s,%s,%s)',
                         (owner,f'{["Finch","AsterPay","CedarCloud"][owner-1]} Weekly Metrics {i:02}',
                          'Historical workspace performance and delivery overview',owner))
        conn.execute('INSERT INTO report_shares(report_id,grantee_org_id) VALUES(2,1)')
        conn.execute("INSERT INTO report_notes(report_id,visibility,body) VALUES(2,'public','Partner view approved for quarterly aggregates only.')")
        conn.execute('INSERT INTO report_notes(report_id,visibility,body) VALUES(2,%s,%s)',
                     ('internal','AsterPay Finance Handoff — restricted reconciliation marker: '+user_flag))
        conn.execute("INSERT INTO report_notes(report_id,visibility,body) VALUES(1,'internal','Pipeline reconciliation owned by Finch operations.')")
        for connector in (1,2,3):
            for i in range(1,241):
                ref=f'{["FIN","AST","CED"][connector-1]}-INV-{i:05}'
                if connector==2 and i==149:
                    ref=root_flag
                conn.execute('INSERT INTO data_rows(connector_id,period,department,amount,reference) VALUES(%s,%s,%s,%s,%s)',
                             (connector,f'2026-{(i%9)+1:02}', ['Retail','Billing','Operations'][i%3],
                              1500+(connector*113)+(i*17),ref))
    print('HELIOS seed complete: three tenants, forty-two reports, private markers')

if __name__=='__main__':
    seed()
