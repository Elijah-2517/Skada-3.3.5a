"""Verify boss-result matching and delayed defeat teardown on real Lua code."""
import unittest

from lupa.lua51 import LuaRuntime
from skada_regression import ADDON, SETUP


class BossResultTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.execute('''
        local function noop() end
        Skada.dummyTable={}; Skada.Debug=noop; Skada.CancelTimer=noop; Skada.SendMessage=noop
        function Skada:SmartStop(set) self.smartstopped=set end
        function Skada:SecureHook(_,_,handler) dbm_end=handler end
        DBM={EndCombat=noop}
        ''')
        source = (ADDON / "Core/Functions.lua").read_text(encoding="utf-8-sig")
        start = source.index("do\n", source.index("-- bossmods callbacks"))
        end = source.index("\n-------------------------------------------------------------------------------", start)
        self.lua.execute("local find,strlower=string.find,string.lower\nlocal Private=Skada.Private\n" + source[start:end])
        self.lua.execute("Skada:SetupBossmod()")

    def check(self, code):
        self.lua.execute(code)

    def test_installed_dbm_encounter_ids_ignore_group_and_localized_name_mismatch(self):
        self.check('''
        local cases={
         {id=24200,main=24200,others={24200,24201}},
         {id=35571,main=34657,others={34657,34701,35571}},
         {id=36476,main=36476},
         {id=34928,main=34928}}
        for _,case in ipairs(cases) do
         Skada.current={gotboss=case.id,mobname='Client NPC title'}
         Skada.tempsets={{}}
         local mod={creatureId=case.main,multiMobPullDetection=case.others,
          combatInfo={mob=case.main,name='Different DBM encounter title'}}
         dbm_end(DBM,mod,false,nil,'onMonsterMessage')
         assert(Skada.current.success and Skada.tempsets[1].success)
        end
        ''')

    def test_wipes_unrelated_encounters_and_snapshots_do_not_become_wins(self):
        self.check('''
        local mod={creatureId=34928,combatInfo={mob=34928,name='Paletress'}}
        Skada.current={gotboss=34928,mobname='Paletress'}
        dbm_end(DBM,mod,true); assert(not Skada.current.success)
        Skada.current={gotboss=36476,mobname='Ick'}
        dbm_end(DBM,mod,false); assert(not Skada.current.success)
        Skada.current={gotboss=34928,mobname='Paletress',snapshotid='death:1:2'}
        dbm_end(DBM,mod,false); assert(not Skada.current.success)
        ''')

    def test_late_dbm_victory_marks_matching_last_fight_only(self):
        self.check('''
        Skada.current={gotboss=36476,mobname='Next boss'}
        Skada.last={gotboss=34928,mobname='Long Paletress title'}
        Skada.tempsets={{}}
        dbm_end(DBM,{combatInfo={mob=34928,name='Short title'}},false)
        assert(Skada.last.success and not Skada.current.success)
        assert(not Skada.tempsets[1].success and not Skada.smartstopped)
        ''')

    def test_missing_and_pattern_names_are_safe_and_plain(self):
        self.check('''
        local mod={combatInfo={name='Boss.one'}}
        Skada.current={gotboss=true,mobname='BossXone'}
        dbm_end(DBM,mod,false); assert(not Skada.current.success)
        Skada.current.mobname='Boss.one'
        dbm_end(DBM,mod,false); assert(Skada.current.success)
        Skada.current={gotboss=true}
        dbm_end(DBM,{combatInfo={}},false); assert(not Skada.current.success)
        dbm_end(DBM,{combatInfo={name=''}},false); assert(not Skada.current.success)
        ''')

    def test_multi_creatures_in_combat_info_and_main_death_event(self):
        self.check('''
        Skada.current={gotboss=24201,mobname='Dalronn'}
        dbm_end(DBM,{combatInfo={mob=24200,name='Group',multiMobPullDetection={24200,24201}}},false)
        assert(Skada.current.success)
        Skada.current={gotboss=35571,mobname='Runok'}
        dbm_end(DBM,{combatInfo={mob=34657,name='Group',killMobs={[35571]=true}}},false)
        assert(Skada.current.success)
        Skada.current={gotboss=36476,mobname='Ick'}
        dbm_end(DBM,{combatInfo={mob=36476}},true,nil,'Main CID Down')
        assert(Skada.current.success)
        ''')

    def load_defeat_timer(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("local function BossDefeated(")
        end = core.index("\nend", start) + 4
        check_start = core.index("\tlocal function check_boss_fight(")
        check_end = core.index("\n\tlocal function check_autostop", check_start)
        finish = core.index("function combat_end()")
        finish_end = core.index("\n\t-- trigger events.", finish)
        reset_start = core.index("function Skada:Reset(force)")
        reset_end = core.index("\nend", reset_start) + 4
        self.lua.execute('''
        local bossdefeat_timer
        local Private={ClearTempUnits=function() end,WaitsForBossmodVictory=Skada.Private.WaitsForBossmodVictory}
        local GetCreatureId=setmetatable({}, {__call=function(_,guid) return tonumber(guid) end})
        local death_events={UNIT_DIED=true}
        local trigger_events={}
        local windows={}
        local function noop() end
        local function create_set(name,set,starttime)
         wipe(set); set.name=name; set.starttime=starttime; set.actors={}; return set
        end
        local check_group,clean_sets=noop,noop
        local dataobj={}; local callbacks={Fire=noop}
        local time,GetTime=function() return 1000 end,function() return 1000 end
        StaticPopup_Hide=noop; Skada.Wipe=noop; Skada.Notify=noop; Skada.CloseMenus=noop
        Skada.CanReset=function() return true end
        function Skada:ScheduleTimer(fn,delay,...)
         queued={fn=fn,args={...}}; return queued
        end
        function Skada:CancelTimer(timer) timer.cancelled=true end
        ''' + core[start:end] + core[check_start:check_end]
                         + core[finish:finish_end] + "\nend\n" + core[reset_start:reset_end] + '''
        function pending_death(id)
         id=id or 36476
         Skada.current={mobname='Client boss name',gotboss=id,type='party'}
         Skada.tempsets={{}}; Skada.bossmod='DBM'
         check_boss_fight(Skada.current,{event='UNIT_DIED',dstGUID=tostring(id)})
        end
        ''')

    def test_pending_kill_is_confirmed_before_combat_teardown(self):
        self.load_defeat_timer()
        self.check('''
        pending_death()
        assert(not Skada.current.success)
        combat_end()
        assert(Skada.current.success and Skada.tempsets[1].success and queued.cancelled)
        ''')

    def test_delayed_kill_cannot_mark_the_next_fight(self):
        self.load_defeat_timer()
        self.check('''
        pending_death()
        Skada.current={mobname='Next',gotboss=1}
        queued.fn(unpack(queued.args))
        assert(not Skada.current.success)
        ''')

    def test_reset_cancels_pending_defeat_before_reusing_current_table(self):
        self.load_defeat_timer()
        self.check('''
        pending_death()
        Skada:Reset(false)
        assert(queued.cancelled and not Skada.current.success)
        combat_end()
        assert(not Skada.current.success)
        ''')

    def test_one_dead_boss_in_managed_multi_boss_encounter_is_not_a_victory(self):
        self.load_defeat_timer()
        self.check('''
        local mod={creatureId=24200,multiMobPullDetection={24200,24201},
         combatInfo={mob=24200,name='Both bosses'}}
        DBM.Mods={mod}
        pending_death(24200)
        assert(not queued,'first boss incorrectly started victory timer')
        dbm_end(DBM,mod,true)
        combat_end(); assert(not Skada.current.success,'wipe became victory')
        dbm_end(DBM,mod,false,nil,'All Mobs Down')
        assert(Skada.current.success,'complete encounter victory missing')
        ''')

    def test_disabled_dbm_module_does_not_block_native_kill_detection(self):
        self.load_defeat_timer()
        self.check('''
        DBM.Mods={{creatureId=24200,multiMobPullDetection={24200,24201},
         Options={Enabled=false},combatInfo={mob=24200,name='Both bosses'}}}
        pending_death(24200)
        assert(queued)
        combat_end(); assert(Skada.current.success)
        DBM.Mods[1].Options.Enabled=true
        DBM.IsEnabled=function() return false end
        queued=nil; pending_death(24200)
        assert(queued,'disabled DBM blocked native detection')
        ''')


if __name__ == "__main__":
    unittest.main()
