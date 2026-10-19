"""Check fork version comparison and mixed raid compatibility."""
import unittest
from lupa.lua51 import LuaRuntime
from skada_regression import ADDON

class VersionTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
        Skada={version='1.8.88-netic.1+fixes.9',website='fork',warnings=0,sent=0}
        L=setmetatable({},{__index=function(_,k) return k end})
        function Skada:Printf(_,url) self.warnings=self.warnings+1; assert(url=='fork') end
        function Skada:SendComm(channel,sender,kind,version) self.sent=self.sent+1; assert(version==self.version) end
        local_gsub=string.gsub
        ''')
        source=(ADDON/"Core/Core.lua").read_text(encoding='utf-8-sig')
        start=source.index('\tfunction convert_version(ver)')
        end=source.index('\n\tfunction check_for_join_and_leave()',start)
        self.lua.execute('local gsub=string.gsub; local match=string.match; '+source[start:end])

    def check(self,code): self.lua.execute(code)

    def test_upstream_and_other_forks_do_not_trigger_warning(self):
        self.check('''
        for _,version in ipairs({'1.8.88','1.8.89-netic.1','999.0.0','1.8.88-netic.1+other.10'}) do
         Skada:VersionCheck('peer',version)
        end
        assert(Skada.warnings==0 and Skada.sent==0 and not Skada.versionChecked)
        ''')

    def test_numeric_revision_comparison(self):
        self.check("Skada:VersionCheck('peer','1.8.88-netic.1+fixes.10'); assert(Skada.warnings==1)")

    def test_old_revision_gets_current_version(self):
        self.check("Skada:VersionCheck('peer','1.8.88-netic.1+fixes.8'); assert(Skada.warnings==0 and Skada.sent==1)")

    def test_equal_peer_does_not_mask_newer_peer(self):
        self.check('''
        Skada:VersionCheck('peer','1.8.88-netic.1+fixes.9')
        Skada:VersionCheck('new','1.8.88-netic.1+fixes.10')
        assert(Skada.warnings==1)
        ''')

    def test_only_one_warning(self):
        self.check('''
        Skada:VersionCheck('peer','1.8.88-netic.1+fixes.10')
        Skada:VersionCheck('other','1.8.88-netic.1+fixes.11')
        assert(Skada.warnings==1)
        ''')

    def test_base_version_precedes_revision(self):
        self.check("Skada:VersionCheck('peer','1.8.89-netic.1+fixes.1'); assert(Skada.warnings==1)")

    def test_invalid_input_is_ignored(self):
        self.check('''
        for _,v in ipairs({false,12,{},'bad','1.8.88-netic.1+fixes.10junk'}) do Skada:VersionCheck('peer',v) end
        Skada:VersionCheck(nil,'1.8.88-netic.1+fixes.10')
        assert(Skada.warnings==0 and Skada.sent==0)
        ''')

if __name__=='__main__': unittest.main(verbosity=2)
