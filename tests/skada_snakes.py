"""Snake Trap units must never reach any combat-log module."""
import unittest
from skada_regression import ADDON
import skada_autostop

class SnakeExclusionTests(unittest.TestCase):
    def setUp(self):
        fixture = skada_autostop.AutostopTests()
        fixture.setUp()
        self.lua = fixture.lua
        self.lua.execute("setup(5,false)")
        source = (ADDON / "Core/Functions.lua").read_text(encoding="utf-8-sig")
        start = source.index("\tfunction Skada:ParseCombatLog(")
        end = source.index("\nend", start)
        self.lua.execute("""
        local ARGS={}
        local Handlers=setmetatable({}, {__index=function() return function(_,_,_,t)
         t.IsGroupEvent=function() return false end; return t
        end end})
        local SWING_EVENTS,ENVIRONMENT_EVENTS,DOT_EVENTS,HOT_EVENTS={},{},{},{}
        local function create_extra_attack() error('snake entered extra-attack queue') end
        local function check_extra_attack() end
        """ + source[start:end] + """
        function feed(t) Skada:ParseCombatLog(nil,1,t.event,t) end
        """)

    def test_all_source_and_destination_events_are_dropped_regardless_of_flags(self):
        self.lua.execute("""
        calls=0
        for _,kind in ipairs({'SWING_DAMAGE','SPELL_DAMAGE','SPELL_PERIODIC_DAMAGE',
         'SPELL_EXTRA_ATTACKS','SPELL_AURA_APPLIED','SPELL_HEAL','SPELL_ENERGIZE','SPELL_SUMMON','UNIT_DIED'}) do
         combatlog_events[kind]={[function() calls=calls+1 end]={}}
         for _,id in ipairs({19833,19921}) do
          for _,flags in ipairs({0,0x814,0x1114}) do
           feed({event=kind,srcGUID=id..'-snake',dstGUID='boss',srcFlags=flags})
           feed({event=kind,srcGUID='hunter',dstGUID=id..'-snake',dstFlags=flags})
          end
         end
        end
        assert(calls==0 and next(guidToOwner)==nil and Skada.LastEvent==nil)
        assert(Skada.current.starttime==10 and not Skada.current.stopped)
        """)

    def test_snakes_cannot_open_a_segment(self):
        self.lua.execute("""
        Skada.current=nil; trigger_events.SPELL_DAMAGE=true
        for _,id in ipairs({19833,19921}) do
         feed({event='SPELL_DAMAGE',srcGUID=id..'-snake',dstGUID='boss',srcName='Snake',dstName='Boss'})
         feed({event='SPELL_DAMAGE',srcGUID='hunter',dstGUID=id..'-snake',srcName='Hunter',dstName='Snake'})
        end
        assert(Skada.current==nil)
        """)

    def test_hunter_other_pets_and_missing_guids_still_dispatch(self):
        self.lua.execute("""
        for _,id in ipairs({'hunter','12345-pet','19834-other'}) do
         feed({event='SPELL_DAMAGE',srcGUID=id,dstGUID='boss'})
        end
        feed({event='SPELL_DAMAGE'})
        assert(recorded==400)
        """)

if __name__ == '__main__': unittest.main()
