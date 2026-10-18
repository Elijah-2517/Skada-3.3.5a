"""Exercise personal death snapshots with the real Lua dispatcher and helpers."""
import unittest

import skada_autostop
from skada_regression import ADDON


class DeathSnapshotTests(unittest.TestCase):
    def setUp(self):
        fixture = skada_autostop.AutostopTests()
        fixture.setUp()
        self.lua = fixture.lua
        init = (ADDON / "Core/Init.lua").read_text(encoding="utf-8-sig")
        start = init.index("function Private.tCopy(")
        end = init.index("\nend", start) + 4
        self.lua.execute(init[start:end])
        start = init.index("function Private.CheckDuplicate(")
        end = init.index("\nend", start) + 4
        self.lua.execute("local strmatch,max,format=string.match,math.max,string.format\n" + init[start:end])
        start = init.index("do\n\tlocal getmetatable", init.index("-- prototypes and binding functions"))
        end = init.index("\nend", start) + 4
        self.lua.execute("local ns=Skada\n" + init[start:end])
        self.lua.execute('''
        local function noop() end
        Skada.Wipe=noop; Skada.UpdateDisplay=noop
        Skada.GetModule=function(self,name) return self.modules[name] end
        Skada.FormatTime=function(_,value) return tostring(value) end
        Skada.GetSetTime=function(_,set) return set.time end
        Skada.maxsets=30; P.setstokeep=15
        windows={}; modes={{SetComplete=function() error('live tracker finalized') end}}
        local oldUnitIsFeignDeath=UnitIsFeignDeath
        UnitIsFeignDeath=function(unit) return oldUnitIsFeignDeath(unit=='player' and 'p1' or unit) end
        ''')
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("local function check_set_name(")
        end = core.index("-- finds a mode", start)
        naming = core[start:core.index("-- process the given set", start)]
        start_clean = core.index("local function clean_sets(")
        start_snapshot = core.index("function Skada:SaveDeathSnapshot(")
        end_snapshot = core.index("\nfunction combat_end()", start_snapshot)
        start_get = core.index("function Skada:GetSet(")
        end_get = core.index("\nend", start_get) + 4
        self.lua.execute('''
        local new,del=Skada.Private.newTable,Skada.Private.delTable
        local copy,CheckDuplicate=Private.tCopy,Private.CheckDuplicate
        local setPrototype=Skada.setPrototype
        local tinsert,tremove=table.insert,table.remove
        local function delete_set(set) wipe(set) end
        ''' + naming + core[start_clean:end] + core[start_snapshot:end_snapshot] + core[start_get:end_get])
        self.lua.execute('''
        function snapshot_setup()
         setup(5,false); P.autostop=false
         byguid.player=byguid.p1; Skada.userGUID='p1'
         Skada.current={starttime=10,name='Current',mobname='Boss',damage=100,
          heal=30,death=0,actors={Player={id='p1',damage=100,heal=30,last=99,
           damagespells={hit={amount=100}},auras={buff={u=2,a=1,s=90}}},
           Enemy={id='boss',enemy=true,damage=5}}}
         Skada.total={damage=100}; Skada.sets={}
         combatlog_events.UNIT_DIED={[function(t)
          Skada.current.death=Skada.current.death+1
         end]={dst_is_interesting_nopets=true}}
        end
        snapshot_setup()
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_own_death_copies_all_modes_and_main_fight_continues(self):
        self.check('''
        die(1)
        local snapshot=Skada.sets[1]
        assert(snapshot and snapshot.damage==100 and snapshot.heal==30 and snapshot.death==1)
        assert(snapshot.time==90 and snapshot.endtime==100 and snapshot.keep)
        assert(snapshot.starttime==Skada.current.starttime and not Skada.current.stopped)
        assert(snapshot.actors.Player.last==nil)
        assert(getmetatable(snapshot)==Skada.setPrototype)
        assert(getmetatable(snapshot.actors.Player)==Skada.playerPrototype)
        assert(getmetatable(snapshot.actors.Enemy)==Skada.enemyPrototype)
        Skada.current.damage=200; Skada.total.damage=200
        Skada.current.actors.Player.damagespells.hit.amount=200
        Skada.current.actors.Player.auras.buff.u=50
        Skada.current.actors.Player.wasted=25 -- late useful-damage correction
        clock=200
        assert(snapshot.damage==100 and snapshot.actors.Player.damagespells.hit.amount==100)
        assert(snapshot.actors.Player.auras.buff.u==2 and not snapshot.actors.Player.wasted)
        assert(snapshot.time==90 and Skada.total.damage==200 and not Skada.tempsets[1].stopped)
        ''')

    def test_only_self_real_death_and_once_per_life(self):
        self.check('''
        die(2); assert(#Skada.sets==0)
        roster[1].feign=true; event('UNIT_DIED','p1'); assert(#Skada.sets==0)
        roster[1].feign=false; die(1); event('UNIT_DIED','p1')
        assert(#Skada.sets==1)
        living(1); Skada.current.damage=150
        die(1); assert(#Skada.sets==2 and Skada.sets[1].damage==150)
        assert(Skada.sets[1].snapshotid~=Skada.sets[2].snapshotid)
        assert(Skada:GetSet(Skada.sets[1].snapshotid)==Skada.sets[1])
        assert(Skada:GetSet(Skada.sets[2].snapshotid)==Skada.sets[2])
        ''')

    def test_death_snapshot_precedes_wipe_stop(self):
        self.check('''
        P.autostop=true; die(2); die(3); die(1)
        assert(#Skada.sets==1 and Skada.sets[1].death==3)
        assert(Skada.current.stopped and Skada.tempsets[1].stopped)
        ''')

    def test_history_selection_restore_and_hard_limit(self):
        self.check('''
        local old={name='Old',starttime=1}; local discarded={name='Discarded',starttime=2}
        Skada.sets={old,discarded}; Skada.maxsets=2
        windows[1]={selectedset=1,restore_set=2}
        die(1)
        assert(Skada.sets[windows[1].selectedset]==old)
        assert(windows[1].restore_set=='current')
        assert(#Skada.sets==2 and Skada.sets[1].snapshotid)
        ''')

    def test_snapshot_is_saved_for_short_nonboss_fights_and_zero_normal_history(self):
        self.check('''
        P.onlykeepbosses=true; P.minsetlength=100; P.setstokeep=0
        Skada.current.mobname=nil; Skada.current.starttime=99
        die(1)
        assert(#Skada.sets==1 and Skada.sets[1].time==1)
        assert(Skada.sets[1].name:find('Death snapshot',1,true))
        ''')

    def test_active_auras_finalize_only_in_snapshot(self):
        self.lua.globals().bit = self.lua.table_from({"band": lambda a, b: int(a) & int(b)})
        self.lua.execute('''
        Skada.IsDisabled=function() return false end
        Skada.ignored_spells.buff={}; Skada.ignored_spells.debuff={}
        ''')

        source = (ADDON / "Modules/Auras.lua").read_text(encoding="utf-8-sig")
        # Load only the shared aura module, including its real finalizer.
        end = source.index("\n---------------------------------------------------------------------------", source.index("\tfunction main:Clean"))
        self.lua.execute(source[:end], "Skada", self.lua.globals().Skada)
        self.check('''
        Skada.modules['Buffs and Debuffs']:OnEnable()
        die(1)
        local frozen=Skada.sets[1].actors.Player.auras.buff
        local live=Skada.current.actors.Player.auras.buff
        assert(frozen.u==12 and frozen.s==nil and frozen.a==nil)
        assert(live.u==2 and live.s==90 and live.a==1)
        ''')

    def test_regenerated_total_excludes_snapshots(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("local function generate_total()")
        end = core.index("\nend", start) + 4
        self.lua.execute('''
        local new=Private.newTable
        local function create_set() return {time=0,actors={}} end
        local function ReloadUI() end
        ''' + core[start:end] + '''
        die(1)
        table.insert(Skada.sets,{starttime=10,endtime=200,time=190,damage=300,
         heal=80,death=2,actors={Player={id='p1',damage=300,heal=80,death=2}}})
        generate_total()
        assert(Skada.total.damage==300 and Skada.total.heal==80 and Skada.total.death==2)
        assert(Skada.total.time==190 and Skada.total.actors.Player.damage==300)
        assert(#Skada.sets==2 and Skada.sets[1].snapshotid)
        ''')

    def test_snapshot_does_not_reset_live_mode_or_total_and_selection_is_unique(self):
        self.check('''
        Skada.modes_set=true
        die(1); local snapshot=Skada.sets[1]
        table.insert(Skada.sets,1,Skada.current)
        assert(Skada:GetSet(snapshot.snapshotid)==snapshot)
        assert(Skada:GetSet(tostring(Skada.current.starttime))==Skada.current)
        assert(Skada.modes_set and Skada.total.damage==100)
        ''')

    def test_only_snapshot_labels_have_native_skull_and_reports_stay_plain(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("\tlocal function set_label_format(")
        end = core.index("\n\tfunction set_window_mode_title", start)
        self.lua.execute('''
        local min,max,format,strmatch=math.min,math.max,string.format,string.match
        local date=function() return '12:00' end
        local SecondsToTime=function() return '1m' end
        ''' + core[start:end])
        self.check('''
        local normal={name='Boss',starttime=10,endtime=100}
        local snapshot={name='Boss - Death snapshot',starttime=10,endtime=100,snapshotid='death:10:100'}
        local icon='|TInterface\\\\TargetingFrame\\\\UI-RaidTargetingIcon_8:14:14|t '
        for fmt=1,8 do
         P.setformat=fmt
         local combined,name=Skada:GetSetLabel(snapshot)
         assert(name==icon..snapshot.name and combined:find(icon,1,true)==1)
         assert(Skada:GetSetLabel(snapshot,true):find(icon,1,true)==1)
         assert(not Skada:GetSetLabel(normal):find('|T',1,true))
         assert(not Skada:GetSetLabel(snapshot,nil,true):find('|T',1,true))
        end
        assert(snapshot.name=='Boss - Death snapshot' and snapshot.starttime==10)
        ''')

    def test_snapshot_freezes_actual_lich_king_useful_damage_exclusions(self):
        self.lua.execute("disabled_modules={}; fresh(); Skada.current.starttime=10; Skada.current.death=0; Skada.current.mobname='Lich King'")
        for file in ("Core/Prototypes.lua", "Modules/Damage.lua"):
            self.lua.execute((ADDON / file).read_text(encoding="utf-8-sig"), "Skada", self.lua.globals().Skada)
        self.check('''
        hit('37695-a','Ghoul',40)
        hit('37799-a','Excluded spirit',30)
        hit('39190-a','Useful spirit',30)
        hit('36597-a','Lich King',70)
        die(1)
        local snapshot=Skada.sets[1]
        assert(snapshot:GetDamage()==170 and snapshot:GetDamage(nil,true)==100)
        assert(snapshot.actors.Player:GetDamage(true)==100)
        hit('36597-a','Lich King',20)
        assert(Skada.current:GetDamage(nil,true)==120)
        assert(snapshot:GetDamage(nil,true)==100 and snapshot:GetDPS(true)==100/90)
        assert(snapshot.actors.Player.damagespells['123.4'].targets.Ghoul.wasted==40)
        ''')


if __name__ == "__main__":
    unittest.main()
