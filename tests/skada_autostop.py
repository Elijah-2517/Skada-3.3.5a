"""Run the real combat dispatcher and stop/resume functions on Lua 5.1."""
import unittest

from lupa.lua51 import LuaRuntime
from skada_regression import ADDON, SETUP


class AutostopTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.execute('''
        Private=Skada.Private
        max=math.max
        local function noop() end
        ignored_events={}; trigger_events={}; spellcast_events={}; death_events={}
        guidToOwner={}; combatlog_events={}; GetCreatureId=Skada.GetCreatureId
        check_cached_names=noop; check_boss_fight=noop
        Skada.Print=noop; Skada.Printf=noop; Skada.RegisterEvent=noop
        Skada.dummyTable={}
        clock=100
        time=function() return clock end; GetTime=time
        roster={}; byguid={}; israid=true; wipes=0; recorded=0
        function UnitGUID(unit) return unit end
        function UnitHealth(unit) return byguid[unit].health end
        function UnitIsDeadOrGhost(unit) return byguid[unit].dead end
        function UnitIsFeignDeath(unit) return byguid[unit].feign end
        function Skada.GetUnitIdFromGUID(guid) return byguid[guid] and guid end
        function Skada.UnitIterator(nopets)
         assert(nopets)
         local i=0
         return function() i=i+1; return roster[i] and roster[i].guid end
        end
        function GetNumGroupMembers() return israid and #roster or #roster-1 end
        function Skada:SendMessage(event)
         if event=='COMBAT_PLAYER_WIPE' then
          wipes=wipes+1; deaths_at_wipe=recorded
         end
        end
        function event(kind,guid,grouped)
         local t={event=kind,dstGUID=guid,dstName=guid}
         function t:DestInGroup(nopets) assert(nopets); return grouped~=false end
         Skada:OnCombatEvent(t)
        end
        function damage() event('SPELL_DAMAGE','boss',false) end
        function die(index,lag)
         local unit=roster[index]
         if not lag then unit.dead=true; unit.health=0 end
         event('UNIT_DIED',unit.guid)
        end
        function living(index)
         local unit=roster[index]; unit.dead=false; unit.health=100
         Skada:UNIT_HEALTH('UNIT_HEALTH',unit.guid)
        end
        ''')
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("\tlocal function check_autostop(")
        end = core.index("\n\tlocal function check_cached_names", start)
        start_dispatch = core.index("\tfunction Skada:OnCombatEvent(")
        start_reset = core.index("\n", core.index("Skada._time = time()", core.index("\tfunction combat_start()")))
        end_reset = core.index("\n\t\tif tentative_timer then", start_reset)
        if "-- Snapshot the roster" in core:
            start_reset = core.index("\t\t-- Snapshot the roster")
            end_reset = core.index("\n\t\tif Skada.current == nil then", start_reset)
        start_stop = core.index("function Skada:StopSegment(")
        end_stop = core.index("function Skada:SetModes()", start_stop)
        # One closure retains the same private state across all event calls.
        self.lua.execute('''
        local dead_members,death_counter,starting_members={},0,0
        function reset_members()
        ''' + core[start_reset:end_reset] + "\nend\n" + core[start:end]
                         + "\n" + core[start_dispatch:core.rfind("\nend")]
                         + "\n" + core[start_stop:end_stop])
        self.lua.execute('''
        function setup(size,raid)
         roster={}; byguid={}; israid=raid~=false
         for i=1,size do
          local unit={guid='p'..i,dead=false,health=100}
          roster[i]=unit; byguid[unit.guid]=unit
         end
         reset_members(); wipes=0; recorded=0; deaths_at_wipe=nil
         Skada.current={starttime=10}; Skada.total={}
         Skada.tempsets={{starttime=20},{starttime=30}}
         Skada.inCombat=true; P.autostop=true
         combatlog_events={UNIT_DIED={
          [function() recorded=recorded+1 end]={dst_is_interesting_nopets=true}},
          SPELL_DAMAGE={[function() recorded=recorded+100 end]={}}}
        end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_threshold_and_last_death_for_solo_party_and_raid(self):
        self.check('''
        for _,size in ipairs({1,2,3,5,10,25,40}) do
         setup(size,size>=10)
         local threshold=math.ceil(size/2)
         for i=1,threshold-1 do die(i); assert(not Skada.current.stopped) end
         die(threshold)
         assert(Skada.current.stopped,'missed threshold for '..size)
         assert(recorded==threshold and deaths_at_wipe==threshold,'last death lost')
         assert(wipes==1)
        end
        ''')

    def test_duplicate_deaths_and_pending_resurrection_do_not_change_count(self):
        self.check('''
        setup(5,false)
        die(1); event('UNIT_DIED','p1'); die(2)
        assert(not Skada.current.stopped,'duplicate death counted twice')
        event('SPELL_RESURRECT','p1'); event('SPELL_RESURRECT','p1')
        Skada:UNIT_HEALTH('UNIT_HEALTH','p1') -- corpse still has zero health
        die(3); assert(Skada.current.stopped,'resurrection offer removed a corpse')
        ''')

    def test_accepted_and_self_resurrections_remove_only_the_living_player(self):
        self.check('''
        for _,selfres in ipairs({false,true}) do
         setup(5,false); die(1); die(2)
         if not selfres then event('SPELL_RESURRECT','p1') end
         living(1); die(3)
         assert(not Skada.current.stopped,'living player still counted dead')
         die(4); assert(Skada.current.stopped)
        end
        ''')

    def test_simultaneous_deaths_before_unit_flags_update(self):
        self.check('''
        setup(5,false)
        die(1,true); die(2,true)
        assert(not Skada.current.stopped)
        die(3,true); assert(Skada.current.stopped,'combat-log deaths lost to stale flags')
        ''')

    def test_disabled_option_outsiders_pets_and_feign_death(self):
        self.check('''
        setup(5,false)
        event('UNIT_DIED','pet',false); event('UNIT_DIED','boss',false)
        roster[1].feign=true; event('UNIT_DIED','p1')
        die(2); die(3); assert(not Skada.current.stopped)
        setup(5,false); P.autostop=false
        for i=1,5 do die(i) end
        assert(not Skada.current.stopped and wipes==0)
        ''')

    def test_no_death_module_and_tentative_segment(self):
        self.check('''
        setup(5,false); combatlog_events.UNIT_DIED=nil
        die(1); die(2); die(3); assert(Skada.current.stopped)
        setup(5,false); Skada.inCombat=false; combatlog_events.UNIT_DIED=nil
        for i=1,5 do die(i) end
        assert(not Skada.current.stopped and wipes==0)
        ''')

    def test_stop_freezes_current_and_phases_until_explicit_resume(self):
        self.check('''
        setup(5,false); die(1); die(2); die(3)
        local sets={Skada.current,Skada.tempsets[1],Skada.tempsets[2]}
        for _,set in ipairs(sets) do
         assert(set.stopped and set.endtime==100 and set.time==100-set.starttime)
        end
        local count=recorded
        clock=200; living(1); living(2); living(3); damage()
        assert(recorded==count and Skada.current.stopped)
        Skada:StopSegment()
        assert(Skada.current.endtime==100 and wipes==1)
        Skada:ResumeSegment()
        for _,set in ipairs(sets) do assert(not set.stopped and not set.endtime) end
        damage(); assert(recorded==count+100)
        ''')

    def test_new_combat_clears_previous_deaths(self):
        self.check('''
        setup(5,false); die(1); die(2); die(3)
        setup(5,false); die(1); die(2)
        assert(not Skada.current.stopped)
        die(3); assert(Skada.current.stopped)
        ''')

    def test_resurrection_health_and_flags_can_arrive_in_either_order(self):
        self.check('''
        setup(5,false); die(1); die(2)
        roster[1].health=100
        Skada:UNIT_HEALTH('UNIT_HEALTH','p1')
        roster[1].dead=false
        Skada:UNIT_HEALTH('UNIT_FLAGS','p1')
        die(3); assert(not Skada.current.stopped)
        die(1); assert(Skada.current.stopped,'second genuine death not counted')
        ''')


if __name__ == "__main__":
    unittest.main()
