import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('ecosystem',Path(__file__).resolve().parents[1]/'scripts/ecosystem.py')
ecosystem=importlib.util.module_from_spec(spec);spec.loader.exec_module(ecosystem)

class MarkdownOwnershipTest(unittest.TestCase):
    def test_vendor_submodule_links_belong_to_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            subprocess.run(['git','init','-q',str(root)],check=True)
            vendor=root/'third_party/core';vendor.mkdir(parents=True)
            (vendor/'.git').write_text('gitdir: ../../.git/modules/core\n')
            (vendor/'README.md').write_text('[upstream-only](absent.md)')
            subprocess.run(['git','-C',str(root),'update-index','--add','--cacheinfo','160000,'+'a'*40+',third_party/core'],check=True)
            self.assertEqual([],ecosystem.check_markdown_links(root))
            (root/'README.md').write_text('[application-owned](missing.md)')
            errors=ecosystem.check_markdown_links(root)
            self.assertEqual(1,len(errors));self.assertIn('missing.md',errors[0])

if __name__=='__main__':unittest.main()
