"""Keep the same pull through player death and missing combat flags."""
import unittest
import skada_death_snapshots
from skada_regression import ADDON

class CombatContinuityTests(unittest.TestCase):
    def setUp(self):
        f=skada_death_snapshots.DeathSnapshotTests(); f.setUp(); self.lua=f.lua
        source=(ADDON/"Core/Functions.lua").read_text(encoding='utf-8-sig')
        start=source.index('do\n',source.index('-- bossmods callbacks'))
        end=source.index('\n-------------------------------------------------------------------------------',start)
        self.lua.execute('local find,strlower=string.find,string.lower; local Private=Skada.Private; '+source[start:end])
        self.lua.execute('''
        Skada.dummyTable={}; Skada.profile=P; ended=0; groupcombat=true
        function InCombatLockdown() return false end
        function IsGroupInCombat() return groupcombat end
        function Skada:UnregisterEvent() end
        function combat_end() ended=ended+1; Skada.current=nil end
        DBM={Mods={{inCombat=true,creatureId=36597,combatInfo={mob=36597,name='The Lich King'}}}}
        Skada.current.gotboss=36597
        ''')
        core=(ADDON/"Core/Core.lua").read_text(encoding='utf-8-sig')
        start=core.index('function Skada:PLAYER_REGEN_ENABLED()'); end=core.index('\nfunction Skada:PLAYER_REGEN_DISABLED()',start)
        self.lua.execute(core[start:end])
        start=core.index('\tlocal function combat_tick()'); end=core.index('\n\tfunction combat_start()',start)
        self.lua.execute(core[start:end]+'\ntick=combat_tick')
        start=core.index('function Window:DisplayMode(mode)'); end=core.index('\nfunction Window:FilterClass',start)
        self.lua.execute('Window={}\n'+core[start:end])

    def check(self,code): self.lua.execute(code)

    def test_stopped_pull_does_not_close_when_player_leaves_combat(self):
        self.check('''
        DBM=nil
        local main=Skada.current; main.stopped=true
        Skada:PLAYER_REGEN_ENABLED()
        assert(ended==0 and Skada.current==main)
        groupcombat=false; Skada:PLAYER_REGEN_ENABLED(); assert(ended==1)
        ''')

    def test_snapshot_and_mode_changes_do_not_restart_active_encounter(self):
        self.check('''
        local main=Skada.current; local start=main.starttime
        die(1); local snapshot=Skada.sets[1]
        local win={selectedset=1,metadata={},db={},Wipe=function() end,clean=function() end}
        setmetatable(win,{__index=Window})
        for _,name in ipairs({'Damage','Healing','Useful Damage'}) do
         win:DisplayMode({isParent=true,moduleName=name})
         assert(win.selectedset==1 and Skada:GetSet(win.selectedset)==snapshot)
        end
        groupcombat=false
        Skada:PLAYER_REGEN_ENABLED(); tick()
        assert(ended==0 and Skada.current==main and main.starttime==start)
        combatlog_events.SPELL_DAMAGE={[function() main.damage=main.damage+50 end]={}}
        clock=120; damage()
        assert(main.damage==150 and snapshot.damage==100 and snapshot.time==90)
        ''')

    def test_wipe_confirmation_allows_normal_completion(self):
        self.check('''
        groupcombat=false; tick(); assert(ended==0)
        DBM.Mods[1].inCombat=false; tick(); assert(ended==1)
        ''')

    def test_other_boss_does_not_keep_pull_open(self):
        self.check('''
        groupcombat=false; DBM.Mods[1].creatureId=123; DBM.Mods[1].combatInfo.mob=123
        tick(); assert(ended==1)
        ''')

    def test_disabled_collection_still_completes_after_encounter(self):
        self.check('''
        groupcombat=false; Skada.disabled=true; DBM.Mods[1].inCombat=false
        tick(); assert(ended==1)
        ''')

    def test_confirmed_victory_does_not_wait_for_dbm_flag_cleanup(self):
        self.check('''
        groupcombat=false; Skada.current.success=true
        tick(); assert(ended==1)
        ''')

if __name__=='__main__': unittest.main(verbosity=2)
