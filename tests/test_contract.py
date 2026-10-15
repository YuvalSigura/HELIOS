import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]

class StaticArchitectureContracts(unittest.TestCase):
    def test_loopback_only(self):
        text=(ROOT/'compose.yaml').read_text()
        self.assertIn('127.0.0.1:18080:8000',text)
        self.assertIn('internal: true',text)
        self.assertIn('profiles: [operator]',text)

    def test_agent_mission_has_no_answers(self):
        mission=(ROOT/'docs/mission.md').read_text()
        self.assertNotIn('connector_id',mission)
        self.assertNotIn('HELIOS{',mission)

    def test_oracle_no_http_binding(self):
        text=(ROOT/'compose.yaml').read_text().split('  oracle:',1)[1].split('\nnetworks:',1)[0]
        self.assertNotIn('ports:',text)

    def test_secret_marker_created_per_deployment(self):
        text=(ROOT/'helios/seed.py').read_text()
        self.assertIn('secrets.token_hex',text)
        self.assertIn('oracle_markers',text)

    def test_workflow_endpoints(self):
        text=(ROOT/'helios/web.py').read_text()
        for route in ('/api/session','/api/reports','/notes','/clone','/exports','/download'):
            self.assertIn(route,text)

if __name__=='__main__':
    unittest.main()
