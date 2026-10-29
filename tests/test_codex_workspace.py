import unittest
from datetime import datetime, timezone
from tools import codex_workspace as w

class WorkspaceTests(unittest.TestCase):
    def snapshot(self, rows=()):
        return {'fetched_at': datetime.now(timezone.utc).isoformat(), 'values':[w.HEADERS, *rows]}
    def job(self, **changes):
        return dict({'id':'j1','company':'Example','role':'Engineer','url':'https://jobs.example/123','country':'DE','location':'Berlin','model':'Hybrid','score':8.5}, **changes)
    def test_germany(self):
        self.assertEqual(w.eligibility(self.job()), 'PASS')
        self.assertEqual(w.eligibility(self.job(country='FR')), 'FAIL')
        self.assertEqual(w.eligibility(self.job(country='',model='Remote')), 'FLAG')
        self.assertEqual(w.eligibility(self.job(country='',model='Remote',remote_countries=['DE'])), 'PASS')
    def test_language(self):
        self.assertEqual(w.language_gate('German','B2',{'German':'A1'}),'FLAG')
        self.assertEqual(w.language_gate('Russian','C1',{'German':'A1'}),'FAIL')
        self.assertEqual(w.language_gate('German','B1',{'German':'None'}),'FAIL')
    def test_score(self):
        self.assertEqual(w.score({'technical':80,'experience':70,'behavioral':60,'career':90}),7.8)
        with self.assertRaises(ValueError): w.score({'technical':float('nan'),'experience':70,'behavioral':60,'career':90})
    def test_tracking_params_removed(self):
        self.assertEqual(w.url_key('https://jobs.example/123?utm_source=x'),w.url_key('https://jobs.example/123'))
        self.assertNotEqual(w.url_key('https://jobs.example/?jobId=1'),w.url_key('https://jobs.example/?jobId=2'))
    def test_linkedin_requisition_identity(self):
        self.assertEqual(w.url_key('https://de.linkedin.com/jobs/view/engineer-1234567890?trk=x'), w.url_key('https://www.linkedin.com/jobs/view/1234567890'))
    def test_private_path_rejected_in_checkout(self):
        with self.assertRaises(ValueError): w.external(w.ROOT/'profile.json')
    def test_workspace_path_escape(self):
        from pathlib import Path
        import tempfile
        root=Path(tempfile.gettempdir())/'workspace'
        self.assertEqual(w.workspace_path(root/'reports'/'x.html',{'paths':{'workspace':str(root)}}),root/'reports'/'x.html')
        with self.assertRaises(ValueError): w.workspace_path(root.parent/'outside.html',{'paths':{'workspace':str(root)}})
    def test_preflight_checks_execution_not_just_presence(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            broken=Path(d)/'broken.exe'; broken.write_text('not an executable')
            cfg={'executables':{k:str(broken) for k in ('bun','lualatex','xelatex')},'paths':{'profile':d},'sources':{}}
            self.assertFalse(w.preflight(cfg)['local_checks']['lualatex'])
    def test_tracker_identity_binding(self):
        cfg={'tracker':{'spreadsheet_id':'correct','sheet':'Tracking'}}
        snap=self.snapshot(); snap.update(spreadsheet_id='wrong',sheet='Tracking')
        with self.assertRaises(ValueError): w.bind_snapshot(snap,cfg)
        snap['spreadsheet_id']='correct'
        self.assertEqual(w.bind_snapshot(snap,cfg),snap)
    def test_report_archive_stages(self):
        events=[{'url':'https://jobs.example/123','stage':'interview'},{'url':'https://jobs.example/123','stage':'offer'}]
        snap=self.snapshot([['Example','Rejected','Engineer','','2026-01-01','https://jobs.example/123']])
        content=w.report(snap,events)
        self.assertIn('Reached interview: 1',content)
        self.assertIn('Received offer: 1',content)
        self.assertIn('filterRows',content)
    def test_submission_readiness(self):
        evidence=dict(compile=True,pages=True,text=True,visual=True,factual=True,review=True)
        self.assertTrue(w.ready(evidence))
        evidence['review']=False
        self.assertFalse(w.ready(evidence))
        self.assertFalse(w.ready({}))
    def test_reordered_live_history(self):
        row=['Example','Rejected','Engineer','','','https://jobs.example/123']
        for rows in ([row,['Other']],[['Other'],row]):
            p=w.propose(self.snapshot(rows),[self.job()],['j1'],'User approved')
            self.assertEqual(p['rows'],[])
    def test_rejected_duplicate(self):
        row=['Example','Rejected','Engineer','','','https://jobs.example/123']
        self.assertEqual(w.duplicate(self.job(),w.records(self.snapshot([row]))),'exact')
    def test_distinct_requisition(self):
        row=['Example','Rejected','Engineer','','','https://jobs.example/123']
        self.assertEqual(w.duplicate(self.job(url='https://jobs.example/456'),w.records(self.snapshot([row]))),'possible')
    def test_approval_required(self):
        with self.assertRaises(ValueError): w.propose(self.snapshot(),[self.job()],[], '')
    def test_empty_tracker_preserves_header(self):
        self.assertEqual(w.propose(self.snapshot(),[self.job()],['j1'],'Approved')['start_row'],2)
    def test_numeric_readback_equivalence(self):
        p=w.propose(self.snapshot(),[self.job(score=8.0)],['j1'],'Approved')
        actual=[list(p['rows'][0])]; actual[0][8]=8
        self.assertTrue(w.verify_rows(p,actual))
    def test_append_after_gaps(self):
        snap=self.snapshot([['Old'],[],['Last']])
        p=w.propose(snap,[self.job()],['j1'],'User approved j1')
        self.assertEqual(p['start_row'],5)
        self.assertEqual(p['rows'][0][1],'Not Applied')
        self.assertEqual(p['rows'][0][4],'')
        self.assertEqual(len(p['rows'][0]),11)
    def test_retry_skips_completed(self):
        p=w.propose(self.snapshot(),[self.job()],['j1'],'Approved j1')
        p2=w.propose(self.snapshot(p['rows']),[self.job()],['j1'],'Approved j1')
        self.assertEqual(p2['rows'],[])
    def test_stale_and_changed_headers(self):
        snap=self.snapshot(); snap['fetched_at']='2000-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError): w.propose(snap,[self.job()],['j1'],'Approved')
        snap=self.snapshot(); snap['values'][0]=['Wrong']
        with self.assertRaises(ValueError): w.records(snap)
    def test_verify_write(self):
        p=w.propose(self.snapshot(),[self.job()],['j1'],'Approved')
        self.assertTrue(w.verify_rows(p,p['rows']))
        self.assertFalse(w.verify_rows(p,[['wrong']]))
    def test_report_escapes_and_counts(self):
        report=w.report(self.snapshot([['<script>','Not Applied','Engineer'],['Other','Submitted (Pending)','Engineer','','2026-01-01']]))
        self.assertIn('&lt;script&gt;',report)
        self.assertNotIn('<script>',report)
        self.assertIn('Submitted: 1',report)
    def test_email_conflict_and_repeat(self):
        self.assertEqual(w.email_proposal('m1','rejection','Submitted (Pending)',{'m1'},1),None)
        self.assertEqual(w.email_proposal('m2','interview','Rejected',set(),1)['action'],'conflict')
        self.assertEqual(w.email_proposal('m2','interview','Submitted (Pending)',set(),2)['action'],'ambiguous')
        self.assertEqual(w.email_proposal('m2','offer','Submitted (Pending)',set(),1)['status'],'Answered positively')

if __name__=='__main__': unittest.main()
