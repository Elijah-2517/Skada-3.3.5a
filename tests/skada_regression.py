"""Run with Python + lupa (Lua 5.1); no WoW client or saved-variable edits."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "Skada"

SETUP = r'''
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
floor = math.floor
format = string.format
local function noop() end
local function copy(t) local r = {} for k,v in pairs(t) do r[k]=v end return r end
L = setmetatable({}, {__index=function(_,k) return k end})
P = {totalidc=true}
healthmax, health, diff, visible = 100, 100, "25h", true
function UnitHealthMax() return healthmax end
function UnitHealth() return health end
function UnitPowerMax() return healthmax end
function UnitExists() return visible end
Skada = {
 Private={newTable=function() return {} end, clearTable=wipe, delTable=wipe,
 copyTable=copy, uformat=string.format},
 Locale=L, profile=P, cacheTable={}, setPrototype={}, actorPrototype={}, enemyPrototype={},
 ignored_spells={damage={},time={}}, ignored_creatures={}, missTypes={},
 grouped_units={[36609]="Important targets",[37970]="Princes overkilling"},
 custom_units={[36609]={name="Valkyrs overkilling",start=0.5,useful=true,
 diff={["10h"]=true,["25h"]=true}}},
 classcolors={format=function(_,name) return name end},
 modules={}, handlers={}, sets={},
}
function Skada.GetCreatureId(guid) return tonumber(string.match(guid,"^(%d+)")) end
function Skada.GetUnitIdFromGUID(guid) if visible then return guid end end
function Skada:GetInstanceDiff() return diff end
function Skada:NewModule(name)
 local m={moduleName=name, NewModule=self.NewModule}
 self.modules = self.modules or {}
 self.modules[name]=m
 return m
end
function Skada:RegisterModule(name, cb)
 if (name=="Damage" or name=="Useful Damage" or name=="Enemy Damage Taken") and not disabled_modules[name] then
  cb(L,P,{},{}); self.modules[name]:OnEnable()
 end
end
function Skada:RegisterForCL(fn,flags,...)
 local events={} for _,e in ipairs({...}) do events[e]=true end
 self.handlers[#self.handlers+1]={fn=fn,events=events}
end
Skada.AddMode=noop; Skada.AddFeed=noop
message_handlers={}; callback_handlers={}
function Skada.RegisterMessage(obj,event,handler)
 message_handlers[event]=message_handlers[event] or {}
 message_handlers[event][obj]=handler
end
function Skada:RegisterCallback(event,handler) callback_handlers[event]=handler end
function fire_message(event)
 for obj,handler in pairs(message_handlers[event] or {}) do
  if type(handler)=="string" then obj[handler](obj,event) else handler(event) end
 end
end
Skada.AddActiveTime=noop; Skada.Debug=noop; Skada.UpdateDisplay=noop
function Skada:FixPets() end
function Skada:FixMyPets(id,name) return id,name end
function Skada:GetActor(set,name,id,flags)
 if not set.actors[name] then
  set.actors[name]=setmetatable({id=id,class="MAGE",enemy=flags==true},
   {__index=flags==true and self.enemyPrototype or self.actorPrototype})
 end
 return set.actors[name]
end
function Skada:FindActor(set,name) return set.actors[name] end
function Skada:GetSetTime() return 10 end
function Skada:GetActiveTime() return 10 end
function Skada:DispatchSets(fn,...)
 fn(self.current,...); fn(self.total,...)
 if self.phase and not self.phase.stopped then fn(self.phase,...) end
end
function fresh()
 Skada.current=setmetatable({name="Current",actors={}},{__index=Skada.setPrototype})
 Skada.total=setmetatable({name="Total",actors={}},{__index=Skada.setPrototype})
end
function hit(id,name,amount,overkill,absorbed,player)
 local t={srcGUID=player or "player",srcName=player or "Player",srcFlags=0,
 dstGUID=id,dstName=name,dstFlags=true,spellid=123,spellstring="123.4",
 amount=amount,overkill=overkill or 0,absorbed=absorbed or 0}
 function t:DestIsBoss() return false end
 for _,h in ipairs(Skada.handlers) do if h.events.SPELL_DAMAGE then h.fn(t) end end
end
function aura(id,spell)
 for _,h in ipairs(Skada.handlers) do
  if h.events.SPELL_AURA_APPLIED then h.fn({dstGUID=id,spellid=spell}) end
 end
end
fresh()
'''


class SkadaTests(unittest.TestCase):
    def setUp(self):
        self.load_runtime()

    def load_runtime(self, disabled=()):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().disabled_modules = self.lua.table_from({name: True for name in disabled})
        source = (ADDON / "Core/Functions.lua").read_text(encoding="utf-8-sig")
        start = source.index("-- heroic valkyr damage")
        end = source.index("-- pet functions", start)
        self.lua.execute("local Private=Skada.Private\n" + source[start:end])
        for name in ("Core/Prototypes.lua", "Modules/Damage.lua", "Modules/Enemies.lua"):
            self.lua.execute((ADDON / name).read_text(encoding="utf-8-sig"), "Skada", self.lua.globals().Skada)

    def check(self, code):
        self.lua.execute(code)

    def load_pet_handling(self):
        self.check('''
        guidToClass={hunter="HUNTER",other="HUNTER"}
        guidToName={hunter="Hunter",other="Other Hunter"}
        guidToOwner=setmetatable({}, {__newindex=function(t,k,v)
         rawset(t,k,v); guidToClass[k]=v
        end})
        Private=Skada.Private
        Private.IsPlayer=function(guid) return guidToName[guid] and 1 or false end
        Private.IsPet=function() return false end -- snake incorrectly flagged as NPC
        Private.EscapeStr=function(s) return s end
        Skada.UnitIterator=function() return function() end end
        Skada.IsMine=function() return false end
        Skada.GetOwnerFlags=function() return 1 end
        Skada.userGUID="hunter"; Skada.userName="Hunter"
        UnitGUID=function(u) return u end
        CreateFrame=function() return setmetatable({}, {__index=function() return function() end end}) end
        folder="Skada"; find=string.find; gsub=string.gsub
        death_events={}; dismiss_pet=function() end
        BITMASK_PETS=12288; BITMASK_GROUP=7
        GetCreatureId=Skada.GetCreatureId
        ARGS_MT={}
        ''')
        self.lua.globals().bit_band = lambda a, b: int(a) & int(b)
        source = (ADDON / "Core/Functions.lua").read_text(encoding="utf-8-sig")
        start = source.index("do\n\tdo\n\t\tlocal GetPetOwnerFromTooltip", source.index("-- pet functions"))
        end = source.index("\n-------------------------------------------------------------------------------", start)
        self.check(source[start:end])
        for name in ("SourceIsPet", "DestIsPet", "SourceInGroup", "DestInGroup"):
            start = source.index(f"\t\t\tfunction ARGS_MT.{name}")
            end = source.index("\n\t\t\tend", start) + len("\n\t\t\tend")
            self.check(source[start:end])
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("local function summon_pet(")
        end = core.index("\nend", start) + len("\nend")
        start_event = core.index("\t\t-- pet summons.")
        end_event = core.index("\n\t\t-- current segment not created?", start_event)
        self.check(core[start:end] + "\nfunction summon(t)\n" + core[start_event:end_event] + "\nend")

    def test_owned_npc_snakes_are_excluded_from_player_only_filters(self):
        self.load_pet_handling()
        self.check('''
        guidToOwner["19833-a"]="hunter"
        local t={srcGUID="19833-a",dstGUID="19833-a",srcFlags=0x814,dstFlags=0x814}
        assert(t.srcFlags==2068)
        assert(ARGS_MT.SourceInGroup(t))
        assert(ARGS_MT.DestInGroup(t))
        assert(not ARGS_MT.SourceInGroup(t,true))
        assert(not ARGS_MT.DestInGroup(t,true))
        ''')

    def test_pet_owner_reassignment_ignores_stale_class_cache(self):
        self.load_pet_handling()
        self.check('''
        guidToOwner["19921-a"]="hunter"
        guidToOwner["19921-a"]="other" -- Lua __newindex does not run on existing keys
        local id,name=Skada:FixMyPets("19921-a","Viper",0)
        assert(id=="other" and name=="Other Hunter")
        id,name=Skada:GetPetOwner("19921-a")
        assert(id=="other" and name=="Other Hunter")
        ''')

    def test_absorbed_damage_class_filter_includes_unabsorbed_actors(self):
        self.check('''
        hit("999-a","Boss",40,0,20,"A")
        hit("999-a","Boss",50,0,0,"B")
        P.absdamage=true
        assert(Skada.current:GetDamage("MAGE")==110)
        Skada.current.actors.A.damaged=40; Skada.current.actors.A.totaldamaged=60
        Skada.current.actors.B.damaged=50
        assert(Skada.current:GetTotal("MAGE",false,"totaldamaged")==110)
        ''')

    def test_absorbed_target_and_source_aggregation(self):
        self.check('''
        P.absdamage=true
        local actor=setmetatable({damage=90,totaldamage=110,damaged=90,totaldamaged=110,
        damagespells={a={targets={Boss={amount=40,total=60}}},b={targets={Boss={amount=50}}}},
        damagedspells={a={sources={Enemy={amount=40,total=60}}},b={sources={Enemy={amount=50}}}}},
        {__index=Skada.actorPrototype})
        local targets=actor:GetDamageTargets(Skada.current,{})
        assert(targets.Boss.amount==90 and targets.Boss.total==110)
        local sources=actor:GetDamageSources(Skada.current,{})
        assert(sources.Enemy.amount==90 and sources.Enemy.total==110)
        ''')

    def test_enemy_tooltip_tolerates_deleted_segment(self):
        self.check('''
        local tooltip={}
        local mode=Skada.modules["Enemy Damage Taken"]
        local win={GetSelectedSet=function() return nil end}
        mode.metadata.post_tooltip(win,"missing","Missing",tooltip)
        ''')

    def test_extension_attribute_hook_and_event_unregistration(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("local function verify_set(")
        end = core.index("\nend", start) + len("\nend")
        self.check(core[start:end] + '''
        local mode={AddPlayerAttributes=function(_,a) a.checked=true end}
        local actor={}
        verify_set(mode,{actors={Player=actor}})
        assert(actor.checked)
        ''')
        start = core.index("\tfunction Skada:RegisterForCL(")
        end = core.index("\n\tlocal function combat_tick", start)
        self.check("local combatlog_events={}\n" + core[start:end] + '''
        local fn=function() end
        Skada:RegisterForCL(fn,{},"SPELL_DAMAGE","SWING_DAMAGE")
        Skada:UnregisterFromCL(fn)
        assert(not combatlog_events.SPELL_DAMAGE[fn])
        assert(not combatlog_events.SWING_DAMAGE[fn])
        ''')

    def test_autostop_counts_dead_destination_and_not_resurrecting_caster(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("\tlocal function check_autostop(")
        end = core.index("\n\tlocal function check_cached_names", start)
        start_call = core.index("\t\t-- autostop on wipe enabled?")
        end_call = core.index("\n\t\t-- stopped or invalid events?", start_call)
        self.check('''
        local death_counter,starting_members=0,4
        Skada.StopSegment=function(self) self.current.stopped=true end
        Skada.SendMessage=function() end
        P.autostop=true
        ''' + core[start:end] + '''
        local function dispatch(self,t)
        ''' + core[start_call:end_call] + '''
        end
        local t={event="UNIT_DIED",SourceInGroup=function() return false end,
        DestInGroup=function() return true end}
        dispatch(Skada,t); assert(death_counter==1)
        t.event="SPELL_RESURRECT"
        t.SourceInGroup=function() return true end
        t.DestInGroup=function() return false end
        dispatch(Skada,t); assert(death_counter==1)
        t.event="UNIT_DIED"; t.DestInGroup=function() return true end
        dispatch(Skada,t); assert(Skada.current.stopped)
        ''')

    def test_combat_end_preserves_historical_set_identity(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start_modes = core.index("function Skada:SetModes()")
        end_modes = core.index("\nend", start_modes) + len("\nend")
        start_end = core.index("function combat_end()")
        end_end = core.index("\nend", start_end) + len("\nend")
        self.check('''
        local new=Skada.Private.newTable
        local function del(t) if type(t)=="table" then wipe(t) end end
        local windows,modes,vehicles={},{},{}
        local callbacks={Fire=function() end}
        local GetCreatureId={}
        local function noop() end
        local time,GetTime=function() return 1000 end,function() return 1000 end
        local IsGroupDead=function() return false end
        local function restore_window_view(win,set,mode)
         win.selectedset=set; win.selectedmode={moduleName=mode}
        end
        Private=Skada.Private; Private.ClearTempUnits=noop
        Skada.SendMessage=noop; Skada.CancelTimer=noop
        P.minsetlength=5
        local retain,remove_set
        local function process_set(set)
         if retain then table.insert(Skada.sets,1,set) end
        end
        local function clean_sets()
         if remove_set then for i=#Skada.sets,1,-1 do
          if Skada.sets[i]==remove_set then table.remove(Skada.sets,i) end
         end end
        end
        ''' + core[start_modes:end_modes] + "\n" + core[start_end:end_end] + '''
        for _,keep in ipairs({false,true}) do
         for phases=0,2 do
          for _,restore in ipairs({false,true}) do
           fresh(); retain=keep; Skada.modes_set=false
           local old={name="Old boss"}; Skada.sets={old}
           local win={selectedset=restore and "current" or 1,
            selectedmode={moduleName="Damage"},db={wipemode="",returnaftercombat=restore},
            Wipe=noop,Toggle=noop,SetSelectedSet=function() error("blind index shift") end}
           if restore then win.restore_set=1; win.restore_mode="Damage" end
           windows[1]=win
           if phases>0 then Skada.tempsets={} for i=1,phases do
            Skada.tempsets[i]={name="Phase",actors={}}
           end end
           combat_end()
           assert(Skada.sets[win.selectedset]==old,"selected historical fight changed")
           assert(not win.restore_set and not win.restore_mode)
          end
         end
        end
        fresh(); retain=true; Skada.modes_set=false
        local old={name="Removed"}; Skada.sets={old}; remove_set=old
        windows[1]={selectedset=1,selectedmode={moduleName="Damage"},db={wipemode=""},
         Wipe=noop,Toggle=noop,SetSelectedSet=function() error("blind index shift") end}
        combat_end(); assert(windows[1].selectedset=="current")
        ''')

    def test_snake_summon_merges_damage_with_correct_hunter(self):
        self.load_pet_handling()
        self.check('''
        P.mergepets=true
        local t={event="SPELL_SUMMON",srcGUID="hunter",dstGUID="19833-a"}
        function t:SourceInGroup() return true end
        function t:DestIsPet() return false end
        summon(t)
        local d={actorid="19833-a",actorname="Snake",actorflags=0,spellid="6603.1"}
        Skada:FixPets(d)
        assert(d.actorid=="hunter" and d.actorname=="Hunter")
        assert(d.petname=="Snake")
        local id,name=Skada:FixMyPets("19833-a","Snake",0)
        assert(id=="hunter" and name=="Hunter")
        local args={srcGUID="19833-a",srcFlags=0,_srcIsPet=false}
        assert(ARGS_MT.SourceIsPet(args,true))
        hit("999-a","Boss",30,0,0,"19833-a")
        assert(Skada.current.actors.Hunter.damage==30)
        assert(not Skada.current.actors["19833-a"])
        t.srcGUID="other"; t.dstGUID="19921-b"; summon(t)
        id,name=Skada:FixMyPets("19921-b","Viper",0)
        assert(id=="other" and name=="Other Hunter")
        ''')

    def test_enemy_snakes_are_not_assigned_to_local_hunter(self):
        self.load_pet_handling()
        self.check('''
        local t={event="SPELL_SUMMON",srcGUID="enemy",dstGUID="19833-enemy"}
        function t:SourceInGroup() return false end
        function t:SourceIsPet() return false end
        function t:DestIsPet() return false end
        summon(t)
        assert(not guidToOwner[t.dstGUID])
        local id,name=Skada:FixMyPets(t.dstGUID,"Snake",0)
        assert(id==t.dstGUID and name=="Snake")
        ''')

    def test_snakes_merge_even_when_other_pets_are_separate(self):
        self.load_pet_handling()
        self.check('''
        P.mergepets=false
        guidToOwner["19921-a"]="hunter"
        local d={actorid="19921-a",actorname="Viper",actorflags=0,spellid="6603.1"}
        Skada:FixPets(d)
        assert(d.actorid=="hunter" and d.actorname=="Hunter")
        guidToOwner["999-pet"]="hunter"
        d={actorid="999-pet",actorname="Wolf",actorflags=0}
        Skada:FixPets(d)
        assert(d.actorid=="999-pet" and d.actorname=="Wolf <Hunter>")
        ''')

    def test_snake_summoned_by_owned_guardian_uses_player_owner(self):
        self.load_pet_handling()
        self.check('''
        guidToOwner["trap"]="other"
        local t={event="SPELL_SUMMON",srcGUID="trap",dstGUID="19833-a"}
        function t:SourceInGroup() return false end
        function t:SourceIsPet() return true end
        function t:DestIsPet() return false end
        summon(t)
        assert(guidToOwner[t.dstGUID]=="other")
        assert(ARGS_MT.DestIsPet({dstGUID=t.dstGUID,_dstIsPet=false},true))
        ''')

    def test_valkyr_heroic_threshold_and_multiple_players(self):
        self.check('''
        hit("36609-a","Valkyr",40,0,0,"A")
        hit("36609-a","Valkyr",30,0,0,"B")
        hit("36609-a","Valkyr",20,0,0,"A")
        assert(Skada.current.actors.A:GetDamage(true)==40)
        assert(Skada.current.actors.B:GetDamage(true)==10)
        assert(Skada.current:GetDamage(nil,true)==50)
        assert(Skada.total:GetDamage(nil,true)==50)
        assert(Skada.current.actors.Valkyr.usefuldamaged==50)
        assert(Skada.current.actors.A.damage==60) -- raw damage unchanged
        ''')

    def test_custom_health_phase_is_calculated_once_for_all_segments(self):
        self.check('''
        Skada.custom_units[36678]={text="%s - Phase 3",start=0.35}
        Skada.phase=setmetatable({name="Phase",actors={}},{__index=Skada.setPrototype})
        hit("36678-a","Putricide",40)
        hit("36678-a","Putricide",30)
        assert(Skada.current.actors["Putricide - Phase 3"].damaged==5)
        assert(Skada.phase.actors["Putricide - Phase 3"].damaged==5)
        assert(Skada.current.actors.Player.damage==70)
        ''')

    def test_custom_first_hit_and_multiple_health_intervals(self):
        self.check('''
        Skada.custom_units[36678]={{name="High",start=1,stop=0.5},
        {name="Low",start=0.5,stop=0.1}}
        hit("36678-a","Putricide",60)
        hit("36678-a","Putricide",60,20)
        assert(Skada.current.actors.High.damaged==50)
        assert(Skada.current.actors.Low.damaged==40)
        assert(Skada.current.actors.Player.overkill==20)
        ''')

    def test_custom_power_phases_do_not_modify_each_other(self):
        self.check('''
        Skada.custom_units[36855]={{name="Mana phase",start=1,power=0},
        {name="Health phase",start=0,power=0}}
        Skada.phase=setmetatable({name="Phase",actors={}},{__index=Skada.setPrototype})
        hit("36855-a","Deathwhisper",40)
        hit("36855-a","Deathwhisper",80)
        hit("36855-a","Deathwhisper",30)
        assert(Skada.current.actors["Mana phase"].damaged==100)
        assert(Skada.current.actors["Health phase"].damaged==50)
        assert(Skada.phase.actors["Mana phase"].damaged==100)
        assert(Skada.phase.actors["Health phase"].damaged==50)
        ''')

    def test_late_valkyr_health_preserves_authors_and_corrects_earlier_hits(self):
        self.check('''
        visible=false
        hit("36609-a","Valkyr",40,0,0,"A")
        visible=true
        hit("36609-a","Valkyr",30,0,0,"B")
        local sources=Skada.current.actors.Valkyr.damagedspells["123.4"].sources
        assert(sources.A.useful==40 and sources.B.useful==10)
        assert(Skada.current.actors.A:GetDamage(true)==40)
        assert(Skada.current.actors.B:GetDamage(true)==10)
        assert(Skada.current.actors.Valkyr.usefuldamaged==50)
        assert(Skada.current.actors["Important targets"].damaged==50)
        ''')

    def test_late_valkyr_health_corrects_previously_crossed_threshold(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70,0,20,"A")
        visible=true; hit("36609-a","Valkyr",10,0,5,"B")
        local sources=Skada.current.actors.Valkyr.damagedspells["123.4"].sources
        assert(sources.A.useful==50 and sources.B.useful==0)
        assert(Skada.current.actors.A:GetDamage(true)==50)
        assert(Skada.current.actors.B:GetDamage(true)==0)
        assert(Skada.total:GetDamage(nil,true)==50)
        assert(Skada.current.actors["Valkyrs overkilling"].damaged==30)
        P.absdamage=true
        assert(Skada.total:GetDamage(nil,true)==70)
        ''')

    def test_late_health_correction_only_updates_original_segments(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70,0,0,"A")
        Skada.phase=setmetatable({name="Phase",actors={}},{__index=Skada.setPrototype})
        visible=true; hit("36609-a","Valkyr",10,0,0,"B")
        assert(Skada.current:GetDamage(nil,true)==50)
        assert(Skada.phase:GetDamage(nil,true)==0)
        assert(not Skada.phase.actors.A)
        assert(Skada.phase.actors.Valkyr.usefuldamaged==0)
        ''')

    def test_valkyr_corrections_independent_of_handler_order_and_enabled_modules(self):
        for disabled in ((), ("Enemy Damage Taken",), ("Damage", "Useful Damage")):
            for reverse in (False, True):
                self.load_runtime(disabled)
                if reverse:
                    self.check('''for i=1,math.floor(#Skada.handlers/2) do
                    local j=#Skada.handlers+1-i
                    Skada.handlers[i],Skada.handlers[j]=Skada.handlers[j],Skada.handlers[i]
                    end''')
                self.check('''
                visible=false; hit("36609-a","Valkyr",70,0,0,"A")
                visible=true; hit("36609-a","Valkyr",10,0,0,"B")
                ''')
                if "Damage" not in disabled:
                    self.check('''assert(Skada.current.actors.A:GetDamage(true)==50)
                    assert(Skada.current.actors.B:GetDamage(true)==0)''')
                if "Enemy Damage Taken" not in disabled:
                    self.check('''local s=Skada.current.actors.Valkyr.damagedspells["123.4"].sources
                    assert(s.A.useful==50 and s.B.useful==0)''')

    def test_late_health_total_without_details_preserves_raw_instance_groups(self):
        self.check('''
        P.totalidc=false; Skada.grouped_units.TRASH=true
        Skada.modules["Enemy Damage Taken"]:CheckZone(nil,"raid")
        visible=false; hit("36609-a","Valkyr",70,0,5,"A")
        hit("36609-a","Valkyr",10,0,10,"A")
        visible=true; hit("36609-a","Valkyr",10,0,20,"B")
        assert(Skada.total:GetDamage(nil,true)==50)
        assert(Skada.total.actors["Important targets"].damaged==50)
        assert(Skada.total.actors["Raid Trash"].damaged==90)
        P.absdamage=true
        assert(Skada.total:GetDamage(nil,true)==55)
        assert(Skada.total.actors["Important targets"].totaldamaged==55)
        assert(Skada.total.actors["Raid Trash"].totaldamaged==125)
        ''')

    def test_reset_discards_corrections_but_preserves_live_target_progress(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70,0,0,"A")
        local reused=Skada.current.actors.A
        callback_handlers.Skada_DataReset()
        fresh(); wipe(reused); reused.id="B"; reused.class="MAGE"
        Skada.current.actors.B=reused
        visible=true; hit("36609-a","Valkyr",10,0,0,"B")
        assert(Skada.current.actors.B:GetDamage(true)==0)
        assert(Skada.current.actors.B.damage==10 and Skada.current.actors.B.wasted==10)
        assert(Skada.current.actors.Valkyr.usefuldamaged==0)
        assert(Skada.current:GetDamage(nil,true)==0)
        ''')

    def test_stopped_phase_receives_only_its_earlier_correction(self):
        self.check('''
        Skada.phase=setmetatable({name="Phase",actors={}},{__index=Skada.setPrototype})
        visible=false; hit("36609-a","Valkyr",70,0,0,"A")
        Skada.phase.stopped=true
        visible=true; hit("36609-a","Valkyr",10,0,0,"B")
        assert(Skada.phase:GetDamage(nil,true)==50)
        assert(Skada.phase.actors.Valkyr.usefuldamaged==50)
        assert(not Skada.phase.actors.B)
        ''')

    def test_final_health_sample_corrects_pending_hits_on_combat_leave(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70)
        visible=true; fire_message("COMBAT_PLAYER_LEAVE")
        assert(Skada.current:GetDamage(nil,true)==50)
        assert(Skada.current.actors.Valkyr.usefuldamaged==50)
        fresh(); hit("36609-a","Valkyr",10)
        assert(Skada.current:GetDamage(nil,true)==10)
        ''')

    def test_unavailable_health_keeps_provisional_modes_consistent(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70)
        assert(Skada.current:GetDamage(nil,true)==70)
        assert(Skada.current.actors.Valkyr.usefuldamaged==70)
        fire_message("COMBAT_PLAYER_LEAVE")
        visible=true; fresh(); hit("36609-a","Valkyr",10)
        assert(Skada.current:GetDamage(nil,true)==10)
        ''')

    def test_correction_updates_spells_and_targets_without_replaying_raw_damage(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",70,0,0,"A")
        visible=true; hit("36609-a","Valkyr",10,0,0,"B")
        local a=Skada.current.actors.A
        local spell=a.damagespells["123.4"]
        assert(a.damage==70 and spell.amount==70 and spell.count==1)
        assert(spell.wasted==20 and spell.targets.Valkyr.wasted==20)
        assert(Skada.current.damage==80)
        assert(Skada.current.actors.Valkyr.damaged==80)
        local target=a:GetDamageTargets(Skada.current,{}).Valkyr
        assert(target.amount==70 and target.wasted==20)
        ''')

    def test_distinct_valkyr_guids_keep_separate_health_and_damage_budgets(self):
        self.check('''
        healthmax=100; hit("36609-a","Valkyr",40,0,0,"A")
        healthmax=200; hit("36609-b","Valkyr",120,0,0,"B")
        hit("36609-a","Valkyr",30,0,0,"A")
        assert(Skada.current.actors.A:GetDamage(true)==50)
        assert(Skada.current.actors.B:GetDamage(true)==100)
        assert(Skada.current.actors.Valkyr.usefuldamaged==150)
        ''')

    def test_generic_phase_with_real_dispatch_and_multiple_phase_segments(self):
        source = (ADDON / "Core/Init.lua").read_text(encoding="utf-8-sig")
        start = source.index("\tfunction ns:DispatchSets(")
        end = source.index("\n\tend", start) + len("\n\tend")
        self.check('''local ns=Skada
        local total_record=function() return false end
        ''' + source[start:end])
        self.check('''
        Skada.custom_units[36678]={text="%s - Phase 3",start=0.35,stop=0.1}
        local p1=setmetatable({name="P1",actors={}},{__index=Skada.setPrototype})
        local p2=setmetatable({name="P2",actors={}},{__index=Skada.setPrototype})
        Skada.tempsets={p1}
        hit("36678-a","Putricide",40)
        p1.stopped=true; Skada.tempsets[2]=p2
        hit("36678-a","Putricide",80,20)
        assert(Skada.current.actors["Putricide - Phase 3"].damaged==25)
        assert(not p1.actors["Putricide - Phase 3"])
        assert(p2.actors["Putricide - Phase 3"].damaged==25)
        assert(not Skada.total.damage)
        ''')

    def test_valkyr_first_hit_crosses_threshold_and_overkill(self):
        self.check('''
        hit("36609-a","Valkyr",120,20)
        assert(Skada.current.actors.Player:GetDamage(true)==50)
        assert(Skada.current.actors.Player.overkill==20)
        assert(Skada.current.actors.Valkyr.usefuldamaged==50)
        assert(Skada.current.actors["Valkyrs overkilling"].damaged==50)
        ''')

    def test_valkyr_normal_and_new_guid(self):
        self.check('''
        diff="25n"; hit("36609-a","Valkyr",80)
        assert(Skada.current.actors.Player:GetDamage(true)==80)
        diff="25h"; hit("36609-b","Valkyr",40)
        assert(Skada.current.actors.Player:GetDamage(true)==120)
        ''')

    def test_rotface_oozes_and_absorbs(self):
        self.check('''
        hit("36627-a","Rotface",100)
        hit("36897-a","Little Ooze",80,0,20)
        hit("36899-a","Big Ooze",50)
        assert(Skada.current:GetDamage(nil,true)==100)
        P.absdamage=true
        assert(Skada.current:GetDamage(nil,true)==100)
        assert(Skada.current.actors.Player:GetDamage(true)==100)
        assert(Skada.current.actors.Player.damage==230)
        ''')

    def test_princes_inactive_active_and_overkill(self):
        self.check('''
        healthmax=1; hit("37970-a","Valanar",60)
        healthmax=1000; hit("37970-a","Valanar",70)
        hit("37972-a","Keleseth",90,89)
        assert(Skada.current:GetDamage(nil,true)==71)
        assert(Skada.current.actors.Player.overkill==89)
        ''')

    def test_legacy_segments_and_ordinary_overkill(self):
        self.check('''
        hit("999-a","Other",120,20)
        assert(Skada.current:GetDamage(nil,true)==100)
        assert(Skada.current.actors.Player:GetDamage(true)==100)
        local old=setmetatable({damage=120,overkill=20},{__index=Skada.actorPrototype})
        assert(old:GetDamage(true)==100)
        ''')

    def test_prince_invocation_switch(self):
        self.check('''
        aura("37970-a",70952)
        hit("37970-a","Valanar",30)
        hit("37972-a","Keleseth",40)
        aura("37972-a",70981)
        hit("37970-a","Valanar",50)
        hit("37972-a","Keleseth",60)
        aura("37973-a",70982)
        hit("37972-a","Keleseth",70)
        hit("37973-a","Taldaram",80)
        assert(Skada.current:GetDamage(nil,true)==170)
        assert(Skada.current.actors.Player.damage==330)
        ''')

    def test_phase_dispatch_does_not_advance_valkyr_twice(self):
        self.check('''
        Skada.phase=setmetatable({name="Phase",actors={}},{__index=Skada.setPrototype})
        hit("36609-a","Valkyr",40)
        hit("36609-a","Valkyr",30)
        assert(Skada.current:GetDamage(nil,true)==50)
        assert(Skada.phase:GetDamage(nil,true)==50)
        assert(Skada.phase.actors.Valkyr.usefuldamaged==50)
        assert(Skada.current.actors.Valkyr.usefuldamaged==50)
        ''')

    def test_valkyr_10h_and_fully_absorbed_hit_below_threshold(self):
        self.check('''
        diff="10h"
        hit("36609-a","Valkyr",40)
        hit("36609-a","Valkyr",30,0,20)
        hit("36609-a","Valkyr",0,0,30)
        assert(Skada.current:GetDamage(nil,true)==50)
        P.absdamage=true
        assert(Skada.current:GetDamage(nil,true)==70)
        assert(Skada.current.actors.Player:GetDamage(true)==70)
        ''')

    def test_retry_missing_unit_and_reset_between_fights(self):
        self.check('''
        visible=false; hit("36609-a","Valkyr",10)
        visible=true; hit("36609-a","Valkyr",10)
        assert(Skada.current.actors.Valkyr.usefuldamaged==20)
        fire_message("COMBAT_PLAYER_LEAVE")
        fresh(); hit("36609-a","Valkyr",40)
        assert(Skada.current:GetDamage(nil,true)==40)
        assert(Skada.current.actors.Valkyr.usefuldamaged==40)
        ''')

    def test_zero_max_health_is_not_cached(self):
        self.check('''
        healthmax=0; hit("36609-a","Valkyr",10)
        healthmax=100; hit("36609-a","Valkyr",10)
        assert(Skada.current.actors.Valkyr.usefuldamaged==20)
        ''')

    def test_useful_spell_target_and_drilldown_views(self):
        self.check('''
        hit("36609-a","Valkyr",40)
        hit("36609-a","Valkyr",30)
        hit("36899-a","Ooze",20)
        local mode=Skada.modules["Useful Damage"]
        local win={actorname="Player",actorid="player",actorclass="MAGE",
        targetname="Valkyr",targetclass="MONSTER",metadata={maxvalue=0},rows={}}
        function win:spell(n,id) self.rows[n]={id=id}; return self.rows[n] end
        function win:actor(n,actor,enemy,name) self.rows[n]={id=name}; return self.rows[n] end
        Skada.FormatValueCols=function() return "" end
        Skada.FormatNumber=function(_,n) return tostring(n) end
        Skada.FormatPercent=function(_,n,total) assert(n==0 or total>0); return "" end
        mode.modules["Spell List"]:Update(win,Skada.current)
        assert(win.rows[1].value==50)
        win.rows={}
        mode.modules["Target List"]:Update(win,Skada.current)
        local sum=0 for _,row in pairs(win.rows) do sum=sum+row.value end
        assert(sum==50)
        win.rows={}
        mode.modules["Target List"].modules["Spell List"]:Update(win,Skada.current)
        assert(win.rows[1].id=="123.4" and win.rows[1].value==50)
        ''')

    def test_all_addon_sources_compile_as_lua51(self):
        compile_lua = self.lua.eval("function(s) local f,e=loadstring(s); return f~=nil,e end")
        for path in (ADDON / "Core").rglob("*.lua"):
            ok, error = compile_lua(path.read_text(encoding="utf-8-sig"))
            self.assertTrue(ok, f"{path.name}: {error}")
        for path in (ADDON / "Modules").glob("*.lua"):
            ok, error = compile_lua(path.read_text(encoding="utf-8-sig"))
            self.assertTrue(ok, f"{path.name}: {error}")

    def test_numeric_history_selection(self):
        core = (ADDON / "Core/Core.lua").read_text(encoding="utf-8-sig")
        start = core.index("\tfunction Window:DisplayModes(settime)")
        end = core.index("\n\tend\nend", start) + len("\n\tend")
        self.check('''
        Window={}; modes={}; tsort=table.sort; user_sort_func=function() end
        click_on_mode=function() end
        Skada.sets={{name="Boss one",starttime=100},{name="Boss two",starttime=200}}
        ''')
        self.check(core[start:end])
        self.check('''
        local win=setmetatable({metadata={},history={},db={},display={},Wipe=function() end},
        {__index=Window})
        win:DisplayModes(2); assert(win.selectedset==2,"numeric segment lost")
        win:DisplayModes("100"); assert(win.selectedset==1)
        win:DisplayModes("current"); assert(win.selectedset=="current")
        win:DisplayModes("total"); assert(win.selectedset=="total")
        ''')


if __name__ == "__main__":
    unittest.main()
