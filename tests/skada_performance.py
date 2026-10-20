"""Verify skipped hot-path work without dropping collected statistics."""
import unittest
from lupa.lua51 import LuaRuntime
from skada_regression import ADDON

class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("Private={IsBossEncounterInProgress=function() return false end}; Skada={}; windows={}; selected_feed=nil; dataobj={}; Window={}; P={}; clock=10; time=function() return clock end")
        self.core=(ADDON/"Core/Core.lua").read_text(encoding="utf-8-sig")

    def load_display(self):
        start=self.core.index("function Skada:UpdateDisplay(force)")
        end=self.core.index("\nend",start)+4
        self.lua.execute(self.core[start:end])
        start=self.core.index("function Window:Wipe(changed)")
        end=self.core.index("\nend",start)+4
        self.lua.execute(self.core[start:end])
        self.lua.execute('''
        function window(selected,mode,set)
         local w={selectedset=selected,selectedmode=mode,calls=0,db={}}
         function w:GetSelectedSet() return set end
         function w:UpdateDisplay() self.calls=self.calls+1; self.changed=nil end
         function w:reset() end
         w.Wipe=Window.Wipe
         windows[#windows+1]=w; return w
        end
        ''')

    def test_absorbs_skips_owner_resolution_for_unabsorbed_hits(self):
        source=(ADDON/"Modules/Absorbs.lua").read_text(encoding="utf-8-sig")
        start=source.index("\tlocal function spell_damage(t)")
        end=source.index("\n\tlocal function spell_heal",start)
        self.lua.execute('''
        resolutions=0; processed=0; shields={Player={}}
        function Skada:FixPetsName(id,name,flags) resolutions=resolutions+1; return name end
        function process_absorb(name,t,partial) processed=processed+1; last_amount=t.absorbed; last_partial=partial end
        '''+source[start:end]+"\nhandle=spell_damage")
        self.lua.execute('''
        for i=1,10000 do
         handle({dstName='Player',amount=100,absorbed=0})
         handle({dstName='Player',amount=100})
        end
        assert(resolutions==0 and processed==0)
        handle({dstName='Player',amount=100,absorbed=30})
        assert(resolutions==1 and processed==1 and last_amount==30 and last_partial)
        handle({dstName='Player',amount=100,absorbed=100})
        assert(processed==2 and not last_partial)
        ''')

    def test_frozen_history_is_not_rebuilt_for_current_events(self):
        self.load_display()
        self.lua.execute('''
        Skada.current={}; Skada.inCombat=true
        local w=window(1,{}, {endtime=10})
        for i=1,100 do Skada.changed=true; Skada:UpdateDisplay() end
        assert(w.calls==0)
        Skada:UpdateDisplay(true); assert(w.calls==1)
        w.changed=true; Skada:UpdateDisplay(); assert(w.calls==2)
        ''')

    def test_live_windows_and_history_menus_keep_refreshing(self):
        self.load_display()
        self.lua.execute('''
        Skada.current={}; Skada.inCombat=true
        local cur=window('current',{},Skada.current)
        local total=window('total',{}, {})
        local phase=window(2,{}, {phase=2})
        local menu=window(nil,nil,nil)
        Skada.changed=true; Skada:UpdateDisplay()
        assert(cur.calls==1 and total.calls==1 and phase.calls==1 and menu.calls==1)
        Skada:UpdateDisplay(); assert(cur.calls==2 and total.calls==2)
        ''')

    def test_wiped_frozen_window_is_rebuilt_once(self):
        self.load_display()
        self.lua.execute('''
        Skada.current={}; Skada.inCombat=true
        local w=window(1,{}, {endtime=10})
        w:Wipe(); assert(w.changed)
        Skada:UpdateDisplay(); assert(w.calls==1)
        Skada.changed=true; Skada:UpdateDisplay(); assert(w.calls==1)
        ''')

    def test_out_of_combat_changes_refresh_history(self):
        self.load_display()
        self.lua.execute('''
        local w=window(1,{}, {endtime=10})
        Skada.changed=true; Skada:UpdateDisplay(); assert(w.calls==1)
        ''')

    def test_feed_still_updates(self):
        self.load_display()
        self.lua.execute('''
        selected_feed=function() return 'DPS' end
        Skada:UpdateDisplay(); assert(dataobj.text=='DPS')
        ''')

    def test_disabled_collection_can_finish_pve_combat(self):
        start=self.core.index("\tlocal function combat_tick()")
        end=self.core.index("\n\tfunction combat_start()",start)
        self.lua.execute('''
        ended=0; lockdown=false; groupcombat=false
        function InCombatLockdown() return lockdown end
        function IsGroupInCombat() return groupcombat end
        function Skada:Debug() end
        function combat_end() ended=ended+1 end
        '''+self.core[start:end]+"\ntick=combat_tick")
        self.lua.execute('''
        Skada.disabled=true; Skada.current={}; Skada.insType='raid'
        lockdown=true; tick(); assert(ended==0)
        lockdown=false; groupcombat=true; tick(); assert(ended==0)
        groupcombat=false; tick(); assert(ended==1)
        Skada.insType='arena'; tick(); assert(ended==1)
        Skada.insType='pvp'; tick(); assert(ended==1)
        Skada.current=nil; tick(); assert(ended==1)
        ''')

if __name__=='__main__': unittest.main(verbosity=2)
