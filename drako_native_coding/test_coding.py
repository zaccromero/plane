import importlib.util,unittest
from pathlib import Path
P=Path(__file__).with_name('coding.py');s=importlib.util.spec_from_file_location('coding',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Contract(unittest.TestCase):
 def test_exact_two_file_catalog(self):self.assertEqual(m.FILES,['bin/context-for-cwd.py','tests/context-for-cwd.test.py']);self.assertEqual(m.protocol.SCHEMAS['write_file']['properties']['path']['enum'],m.FILES)
 def test_parameter_free_or_enum_scoped(self):
  w=m.Worker('/not-used')
  for name,args in [('shell',{}),('write_file',{'path':'../settings.json','content':'no'}),('write_file',{'path':m.FILES[0],'content':'x'*32001}),('run_tests',{'command':'no'})]:
   with self.assertRaises(RuntimeError):w.call(name,args)
 def test_tool_inventory(self):self.assertEqual(len(m.TOOLS),5);self.assertTrue(all(x.startswith('mcp__drako_code__') for x in m.TOOLS))
if __name__=='__main__':unittest.main()
