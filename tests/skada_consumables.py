"""Consumables (Potions.lua) and armor debuffs (SunderCounter.lua). Python + lupa (Lua 5.1)."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ADDON = Path(__file__).resolve().parents[1] / "Skada"

SETUP = r'''
local function noop() end
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
GetTime = function() return NOW end
NOW = 100
GetItemInfo = function(i) return "item" .. tostring(i) end
GetSpellInfo = function(i) return "spell" .. i, nil, "icon" end
GetSpellLink = function(i) return "link" .. i end
GameTooltip = {SetHyperlink = noop, Hide = noop}
UnitGUID = function(u) return u end
UnitName = function(u) return u end
UnitBuff = function(unit, i) local b = (BUFFS or {})[unit]; local s = b and b[i]; if s then return "aura", nil, nil, nil, nil, nil, nil, nil, nil, nil, s end end
timers = {}
L = setmetatable({}, {__index = function(_, k) return k end})
Skada = {
 Private = {newTable = function() return {} end, clearTable = wipe, delTable = function() end,
  uformat = string.format, DEFAULT_FLAGS = 1},
 classcolors = {format = function(_, n) return n end},
 spellnames = setmetatable({}, {__index = function(_, k) return "s" .. k end}),
 dummyTable = {}, modules = {}, sets = {}, changed = false,
 callbacks = {},
}
Skada.UnitIterator = function() local i = 0; local list = ROSTER or {}
  return function() i = i + 1; return list[i] end end
Skada.RegisterCallback = noop; Skada.RegisterMessage = noop
Skada.UnregisterAllCallbacks = noop; Skada.UnregisterAllMessages = noop
Skada.AddMode = noop; Skada.RemoveMode = noop; Skada.UnregisterFromCL = noop
Skada.ScheduleTimer = function(_, fn, d, ...) timers[#timers + 1] = {fn = fn, args = {...}}; return #timers end
Skada.CancelTimer = function(_, id) if timers[id] then timers[id].dead = true end end
Skada.GetActor = function(_, set, name, id, flags)
  set.actors = set.actors or {}
  set.actors[name] = set.actors[name] or {id = id, flag = flags}
  return set.actors[name]
end
Skada.EnsureTotalSet = function(self)
  if not self.total then self.total = self.sets[0] or {actors = {}}; self.sets[0] = self.total end
  return self.total
end
Skada.DispatchSets = function(self, fn, ...)
  if self.current then fn(self.current, ...) end
  if self.total then fn(self.total, ...) end
end
local modules = {}
Skada.RegisterModule = function(_, name, fn) modules[name] = fn end
local function newmod(name)
  local m = {name = name}
  m.NewModule = function(_, n) return newmod(n) end
  return m
end
Skada.NewModule = function(_, n) local m = newmod(n); Skada.modules[n] = m; return m end
CL = {}
Skada.RegisterForCL = function(_, fn, flags, ...) CL[#CL + 1] = {fn = fn, events = {...}} end
Skada.Printf = noop
function load_module(name, src, settings)
  assert(loadstring(src, name))(name, Skada)
  modules[name](L, {prepotion = true}, {}, {}, settings or {sunderdelay = 3}, {tweaks = {args = {general = {args = {}}}}})
  return Skada.modules[name]
end
function ev(t)
  t.DestInGroup = function() return true end
  t.SourceInGroup = function() return true end
  t.DestIsBoss = function() return false end
  return t
end
function reset_state()
  Skada.sets = {}; Skada.total = nil; Skada.current = nil; Skada.inCombat = false
  timers = {}; BUFFS = nil; ROSTER = nil
end
'''


class ConsumablesTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        src = (ADDON / "Modules/Potions.lua").read_text(encoding="utf-8-sig")
        self.lua.globals().POTIONS_SRC = src
        self.check('''
        mode = load_module("Potions", POTIONS_SRC)
        mode:OnInitialize()
        reset_state()
        function cast(name, spell, ts)
          mode:CombatEvent(nil, ev{event="SPELL_CAST_SUCCESS", spellid=spell, srcName=name,
            srcGUID="g"..name, srcFlags=1, timestamp=ts})
        end
        function start_combat() Skada.current = {actors = {}}; mode:CombatEnter(); Skada.inCombat = true end
        function total(name) local a = Skada.total.actors[name]; return a and a.potion or 0 end
        function cur(name) local a = Skada.current.actors[name]; return a and a.potion or 0 end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_prepared_potion_goes_to_total_once_and_into_next_pull(self):
        self.check('''
        cast("War", 53762, 1)               -- outside combat, a known potion spell
        assert(total("War") == 1)
        start_combat()
        assert(cur("War") == 1 and total("War") == 1)
        Skada.sets.consumables.pending = Skada.sets.consumables.pending
        assert(next(Skada.sets.consumables.pending) == nil)
        ''')

    def test_in_combat_potion_and_long_gap_and_hunter_repeats(self):
        self.check('''
        start_combat()
        cast("Hunt", 53762, 10); cast("Hunt", 53762, 70); cast("Hunt", 53762, 700)
        assert(cur("Hunt") == 3 and total("Hunt") == 3)
        ''')

    def test_prepot_speed_and_armor_reach_current_and_repeats_work_for_any_class(self):
        self.check('''
        cast("War", 53762, 1); cast("War", 53908, 2); cast("Lock", 53908, 3)
        start_combat()
        assert(cur("War") == 2 and total("War") == 2 and cur("Lock") == 1)
        cast("Lock", 53908, 70); cast("Lock", 53908, 140); cast("War", 53908, 200)
        assert(cur("Lock") == 3 and total("Lock") == 3 and cur("War") == 3 and total("War") == 3)
        ''')

    def test_duplicate_delivery_same_timestamp_counts_once(self):
        self.check('''
        start_combat()
        cast("War", 53762, 10); cast("War", 53762, 10)
        assert(cur("War") == 1 and total("War") == 1)
        ''')

    def test_long_flask_counts_total_only(self):
        self.check('''
        cast("War", 53758, 1)               -- long-lasting flask
        start_combat()
        assert(total("War") == 1 and cur("War") == 0)
        cast("War", 53758, 500)
        assert(cur("War") == 0)
        ''')

    def test_food_counts_once_per_applied_event(self):
        self.check('''
        local function food(ts) mode:CombatEvent(nil, ev{event="SPELL_AURA_APPLIED", spellid=57356,
          dstName="War", dstGUID="gWar", dstFlags=1, timestamp=ts}) end
        food(5); food(5)
        assert(total("War") == 1)
        ''')

    def test_preexisting_flask_is_inferred_once(self):
        self.check('''
        ROSTER = {"p1"}; BUFFS = {p1 = {53758}}
        start_combat(); start_combat()
        local a = Skada.total.actors.p1
        assert(a and a.potion == 1 and a.potioninferred["46379"])
        assert(cur("p1") == 0)
        ''')

    def test_reset_clears_and_restore_total_rebuilds_without_duplicates(self):
        self.check('''
        cast("War", 53762, 1); cast("War", 53758, 2)
        assert(total("War") == 2)
        Skada.total.actors.War.potion = 99          -- history regeneration wiped / altered it
        mode:RestoreTotal(); mode:RestoreTotal()
        assert(total("War") == 2 and Skada.total.potion == 2)
        mode:DataReset()
        assert(Skada.sets.consumables == nil)
        ''')


class SunderTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().SUNDER_SRC = (ADDON / "Modules/SunderCounter.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        local settings = {sunderdelay = 3}
        mode = load_module("Sunder Counter", SUNDER_SRC, settings)
        mode.metadata = nil
        mode:OnEnable()
        Skada.current = {actors = {}}
        Skada.total = {actors = {}}
        sunder = CL[1].fn
        function aura(event, spell, src, dst, extra)
          local t = ev{event=event, spellid=spell, srcName=src, srcGUID="g"..src, srcFlags=1,
            dstName=dst, dstGUID="g"..dst}
          for k, v in pairs(extra or {}) do t[k] = v end
          sunder(t)
        end
        function count(set, name) local a = set.actors[name]; return a and a.sunder or 0 end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_each_source_is_credited_for_its_own_aura(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 7386, "W1", "Boss")
        aura("SPELL_AURA_APPLIED_DOSE", 47467, "W2", "Boss", {amount = 2})
        assert(count(Skada.current, "W1") == 1 and count(Skada.current, "W2") == 1)
        ''')

    def test_other_armor_effects_are_separate_and_not_blocked_by_sunder_delay(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 47467, "W1", "Boss", {amount = 1})
        aura("SPELL_AURA_APPLIED", 64382, "W1", "Boss")
        aura("SPELL_AURA_APPLIED", 48669, "R1", "Boss")
        local a = Skada.current.actors
        assert(a.W1.sunder == 2 and a.R1.sunder == 1)
        assert(a.W1.sunderspells[47467] == 1 and a.W1.sunderspells[64382] == 1)
        assert(a.R1.sunderspells[8647] == 1)
        ''')

    def test_useless_sunder_refresh_is_skipped_but_other_spells_refresh_counts(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 47467, "W1", "Boss", {amount = 5})
        aura("SPELL_AURA_REFRESH", 47467, "W1", "Boss")
        assert(count(Skada.current, "W1") == 1)
        aura("SPELL_AURA_REFRESH", 8647, "R1", "Boss")
        aura("SPELL_AURA_REFRESH", 8647, "R1", "Boss")
        assert(count(Skada.current, "R1") == 2)
        ''')

    def test_sunder_counted_in_current_and_total(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 64382, "W1", "Boss")
        aura("SPELL_AURA_APPLIED", 48669, "R1", "Boss")
        assert(count(Skada.current, "W1") == 1 and count(Skada.total, "W1") == 1)
        assert(count(Skada.current, "R1") == 1 and count(Skada.total, "R1") == 1)
        assert(Skada.total.sunder == 2)
        ''')

    def test_removal_and_unrelated_spells_do_not_count(self):
        self.check('''
        aura("SPELL_AURA_REMOVED", 47467, "W1", "Boss")
        aura("SPELL_AURA_APPLIED", 12345, "W1", "Boss")
        assert(count(Skada.current, "W1") == 0)
        ''')


if __name__ == "__main__":
    unittest.main()
