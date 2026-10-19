"""Check late talent inspection on the real actor lookup code."""
import unittest
from lupa.lua51 import LuaRuntime
from skada_regression import ADDON, SETUP

class SpecTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.execute(r'''
        Skada.validclass={SHAMAN=true}; Skada.modes={}
        Skada.Private.guidToClass={player="SHAMAN"}; Skada.Private.guidToName={}
        Skada.playerPrototype={Bind=function(_,a) return a end}
        Skada.actorPrototype.Bind=Skada.playerPrototype.Bind
        Skada.enemyPrototype.Bind=Skada.playerPrototype.Bind
        Skada.userGUID="self"; Skada.userClass="SHAMAN"
        Skada.spec_to_role={[262]="DAMAGER",[263]="DAMAGER",[264]="HEALER"}
        Skada.spell_to_spec={}
        inspected_spec, inspected_talent, inspected_role=nil,nil,nil
        function Skada.GetUnitSpec() return inspected_spec,inspected_talent end
        function Skada.GetUnitRole() return inspected_role end
        function seed(set)
         set.actors.Player={id="player",class="SHAMAN",spec=263,role="DAMAGER",talent="18/53/0"}
         return set.actors.Player
        end
        function inspect(spec,talent,role)
         inspected_spec,inspected_talent,inspected_role=spec,talent,role
        end
        ''')
        source=(ADDON / "Core/Functions.lua").read_text(encoding="utf-8-sig")
        start=source.index("do\n",source.index("-- player & enemies functions"))
        stop=source.index("\n-------------------------------------------------------------------------------",start)
        self.lua.execute("local Private=Skada.Private; local new=Private.newTable; "
                         "local guidToClass=Private.guidToClass; local guidToName=Private.guidToName; "
                         "local L=Skada.Locale; local strmatch=string.match; " + source[start:stop])

    def check(self, code):
        self.lua.execute(code)

    def test_late_inspection_corrects_current_total_and_phase(self):
        self.check('''
        local phase={actors={}}
        for _,set in ipairs({Skada.current,Skada.total,phase}) do seed(set) end
        inspect(264,"0/13/58","HEALER")
        for _,set in ipairs({Skada.current,Skada.total,phase}) do
         local a=Skada:GetActor(set,"Player","player")
         assert(a.spec==264 and a.role=="HEALER" and a.talent=="0/13/58" and a.__mod)
        end
        ''')

    def test_missing_inspection_preserves_known_spec(self):
        self.check('''
        local a=seed(Skada.current)
        for _,spec in ipairs({0,false}) do
         inspect(spec,nil,"NONE"); Skada:GetActor(Skada.current,"Player","player")
         assert(a.spec==263 and a.talent=="18/53/0" and a.role=="DAMAGER")
        end
        ''')

    def test_self_updates_without_roster_cache(self):
        self.check('''
        local a=seed(Skada.current); a.id="self"
        inspect(264,"0/13/58","HEALER")
        Skada:GetActor(Skada.current,"Player","self")
        assert(a.spec==264 and a.role=="HEALER")
        ''')

    def test_other_segments_and_snapshots_are_untouched(self):
        self.check('''
        seed(Skada.current)
        local old={actors={}}; local snapshot={actors={},deathsnapshot=true}
        local a,b=seed(old),seed(snapshot)
        inspect(264,"0/13/58","HEALER")
        Skada:GetActor(Skada.current,"Player","player")
        assert(a.spec==263 and b.spec==263)
        ''')

    def test_non_roster_actor_keeps_recorded_spec(self):
        self.check('''
        local a=seed(Skada.current); Skada.Private.guidToClass.player=nil
        inspect(264,"0/13/58","HEALER")
        Skada:GetActor(Skada.current,"Player","player")
        assert(a.spec==263)
        ''')

    def test_same_spec_refreshes_talent_distribution(self):
        self.check('''
        local a=seed(Skada.current)
        inspect(263,"16/55/0","DAMAGER")
        Skada:GetActor(Skada.current,"Player","player")
        assert(a.spec==263 and a.talent=="16/55/0")
        ''')

    def test_missing_role_uses_confirmed_spec(self):
        self.check('''
        local a=seed(Skada.current)
        inspect(264,"0/13/58","NONE")
        Skada:GetActor(Skada.current,"Player","player")
        assert(a.spec==264 and a.role=="HEALER")
        ''')

if __name__ == "__main__":
    unittest.main(verbosity=2)
