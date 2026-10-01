import json
from pathlib import Path
import unittest
from timerapp_ag.sync_protocol import *

class ProtocolV2Tests(unittest.TestCase):
    def test_shared_fixtures(self):
        cases=json.loads((Path(__file__).parent/'fixtures/sync-v2/cases.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                merged=merge_documents(case['left'],case['right'])
                self.assertEqual(merged,merge_documents(case['right'],case['left']))
                self.assertEqual(merged,merge_documents(merged,merged))
                projected=project_document(merged)
                entity=next(e for e in projected['entities'] if e['entity']==case.get('entity',['task','t']))
                for field,value in case.get('expectedFields',{}).items():
                    self.assertEqual(entity['values'][field],value)
                if 'expectedDeleted' in case:self.assertEqual(entity['deleted'],case['expectedDeleted'])
                self.assertEqual(sorted(c['field'] for c in projected['conflicts']),case['expectedConflictFields'])
    def test_numbers_and_boolean(self):
        self.assertTrue(equal(1,1.0));self.assertFalse(equal(True,1))
    def test_invalid_interval(self):
        with self.assertRaises(ValueError):change_entity(empty_document(),'a',['session','t','s'],{'interval':{'id':'other'}})
