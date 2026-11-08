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
GetItemIcon = function(i) if i ~= 40211 then return "ICON" .. i end end
GetSpellInfo = function(i) return "spell" .. i, nil, "icon" end
GetSpellLink = function(i) return "link" .. i end
GameTooltip = {SetHyperlink = noop, Hide = noop}
UnitGUID = function(u) return u end
UnitName = function(u) return u end
UnitBuff = function(unit, i) local b = (BUFFS or {})[unit]; local s = b and b[i]; if s then return "aura", nil, nil, nil, nil, nil, nil, "caster", nil, nil, s end end
timers = {}
L = setmetatable({}, {__index = function(_, k) return k end})
Skada = {
 Private = {newTable = function() return {} end, clearTable = wipe, delTable = function() end,
  uformat = string.format, DEFAULT_FLAGS = 1, guidToClass = {}},
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

    def test_prepotion_message_shows_icons_once_per_player(self):
        self.check('''
        function Skada:Printf(_, text) PRINTED = text end
        cast("War", 53762, 1); cast("War", 53762, 2); cast("War", 53909, 3)
        cast("Lock", 53908, 4)              -- no icon available: falls back to the item name
        start_combat(); mode:CombatLeave()
        assert(PRINTED:find("War ", 1, true) == PRINTED:find("War", 1, true))
        local _, wars = PRINTED:gsub("War", "")
        assert(wars == 1, PRINTED)
        assert(PRINTED:find("ICON40093:14:14", 1, true) and PRINTED:find(" x2", 1, true), PRINTED)
        assert(PRINTED:find("ICON40212:14:14", 1, true), PRINTED)
        assert(PRINTED:find("Lock item40211", 1, true), PRINTED)
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

    def test_food_is_not_counted(self):
        self.check('''
        start_combat()
        mode:CombatEvent(nil, ev{event="SPELL_AURA_APPLIED", spellid=57356,
          dstName="War", dstGUID="gWar", dstFlags=1, timestamp=5})
        assert((Skada.total == nil or total("War") == 0) and cur("War") == 0)
        ''')

    def test_food_from_older_builds_is_removed_from_total_and_ledger(self):
        self.check('''
        Skada.total = {actors = {War = {potion = 3, potionspells = {s57356 = 1, ["40093"] = 2}}}, potion = 3}
        Skada.sets[0] = Skada.total
        Skada.sets.consumables = {pending = {}, known = {}, initialized = true,
          ledger = {consumableledger = true, potion = 3, actors = {War = {potion = 3, potionspells = {s57356 = 1, ["40093"] = 2}}}}}
        cast("War", 53762, 1)
        local a = Skada.total.actors.War
        assert(a.potion == 3 and a.potionspells.s57356 == nil and a.potionspells["40093"] == 3)
        assert(Skada.total.potion == 3)
        local l = Skada.sets.consumables.ledger.actors.War
        assert(l.potion == 3 and l.potionspells.s57356 == nil)
        mode:RestoreTotal()
        assert(Skada.total.actors.War.potion == 3)
        ''')

    def test_preexisting_flask_is_inferred_once(self):
        self.check('''
        ROSTER = {"p1"}; BUFFS = {p1 = {53758}}
        start_combat(); start_combat()
        local a = Skada.total.actors.p1
        assert(a and a.potion == 1 and a.potioninferred["46379"])
        assert(cur("p1") == 0)
        ''')

    def test_flask_drunk_before_manual_reset_returns_on_first_pull(self):
        self.check('''
        mode:CombatEvent(nil, ev{event="SPELL_CAST_SUCCESS", spellid=53758, srcName="p1",
          srcGUID="p1", srcFlags=1, timestamp=1})
        mode:DataReset(); Skada.total = nil; Skada.sets[0] = nil
        ROSTER = {"p1"}; BUFFS = {p1 = {53758}}
        start_combat()
        local a = Skada.total.actors.p1
        assert(a and a.potion == 1 and a.potioninferred["46379"])
        ''')

    def test_total_segment_allows_opening_a_players_consumables(self):
        self.check('''
        mode:OnEnable()
        assert(mode.metadata.click1 and not mode.metadata.click1.nototal)
        cast("War", 53762, 1); cast("War", 53908, 2)
        local spells = Skada.total.actors.War.potionspells
        assert(spells["40093"] == 1 and spells["40211"] == 1)
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
        aura("SPELL_AURA_APPLIED", 58567, "W1", "Boss")
        aura("SPELL_AURA_APPLIED_DOSE", 58567, "W2", "Boss", {amount = 2})
        assert(count(Skada.current, "W1") == 1 and count(Skada.current, "W2") == 1)
        ''')

    def test_other_armor_effects_are_separate_and_not_blocked_by_sunder_delay(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 58567, "W1", "Boss", {amount = 1})
        aura("SPELL_AURA_APPLIED", 64382, "W1", "Boss")
        aura("SPELL_AURA_APPLIED", 48669, "R1", "Boss")
        local a = Skada.current.actors
        assert(a.W1.sunder == 2 and a.R1.sunder == 1)
        assert(a.W1.sunderspells[47467] == 1 and a.W1.sunderspells[64382] == 1)
        assert(a.R1.sunderspells[8647] == 1)
        ''')

    def test_useless_sunder_refresh_is_skipped_but_other_spells_refresh_counts(self):
        self.check('''
        aura("SPELL_AURA_APPLIED", 58567, "W1", "Boss", {amount = 5})
        aura("SPELL_AURA_REFRESH", 58567, "W1", "Boss")
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

    def test_real_sunder_debuff_id_from_the_combat_log_is_counted(self):
        self.check('''
        -- 3.3.5a log: cast 7386, then the debuff 58567 is applied/stacked/refreshed.
        aura("SPELL_AURA_APPLIED", 58567, "W1", "Boss", {amount = 1})
        aura("SPELL_AURA_APPLIED_DOSE", 58567, "W1", "Boss", {amount = 2})
        aura("SPELL_AURA_APPLIED_DOSE", 58567, "W2", "Boss", {amount = 3})
        assert(count(Skada.current, "W1") == 2 and count(Skada.current, "W2") == 1)
        assert(Skada.current.actors.W1.sunderspells[47467] == 2)
        ''')

    def test_removal_and_unrelated_spells_do_not_count(self):
        self.check('''
        aura("SPELL_AURA_REMOVED", 58567, "W1", "Boss")
        aura("SPELL_AURA_APPLIED", 12345, "W1", "Boss")
        assert(count(Skada.current, "W1") == 0)
        ''')


class PowerBuffTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().PB_SRC = (ADDON / "Modules/PowerBuffs.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        mode = load_module("Power Buffs", PB_SRC)
        mode:OnEnable()
        Skada.current = {actors = {}}
        Skada.total = {actors = {}}
        applied = CL[1].fn
        function buff(event, spell, dst, ts, src)
          applied(ev{event=event, spellid=spell, dstName=dst, dstGUID="g"..dst, dstFlags=1, timestamp=ts,
            srcName=src or "Giver"})
        end
        function pb(set, name) local a = set.actors[name]; return a and a.powerbuff or 0 end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_each_power_buff_counts_for_the_receiver_in_current_and_total(self):
        self.check('''
        buff("SPELL_AURA_APPLIED", 10060, "Mage", 1)    -- Power Infusion
        buff("SPELL_AURA_APPLIED", 57933, "Mage", 2)    -- Tricks of the Trade
        buff("SPELL_AURA_APPLIED", 49016, "Rogue", 3)   -- Hysteria
        buff("SPELL_AURA_APPLIED", 23060, "Rogue", 4)   -- Battle Squawk
        buff("SPELL_AURA_REFRESH", 23060, "Rogue", 9)   -- another squawk
        assert(pb(Skada.current, "Mage") == 2 and pb(Skada.total, "Mage") == 2)
        assert(pb(Skada.current, "Rogue") == 3)
        local s = Skada.current.actors.Rogue.powerbuffspells
        assert(s[49016] == 1 and s[23060] == 2)
        ''')

    def test_duplicates_and_other_buffs_are_ignored(self):
        self.check('''
        buff("SPELL_AURA_APPLIED", 10060, "Mage", 5); buff("SPELL_AURA_APPLIED", 10060, "Mage", 5)
        buff("SPELL_AURA_APPLIED", 48470, "Mage", 6)    -- Gift of the Wild
        buff("SPELL_AURA_APPLIED", 57934, "Mage", 7)    -- Tricks redirect on the rogue, not the buff
        assert(pb(Skada.current, "Mage") == 1)
        ''')

    def test_sources_are_recorded_per_buff(self):
        self.check('''
        buff("SPELL_AURA_APPLIED", 57933, "Mage", 1, "Rogue1")
        buff("SPELL_AURA_APPLIED", 57933, "Mage", 2, "Rogue2")
        buff("SPELL_AURA_APPLIED", 57933, "Mage", 3, "Rogue1")
        buff("SPELL_AURA_APPLIED", 10060, "Mage", 4, "Priest")
        local src = Skada.total.actors.Mage.powerbuffsources
        assert(src[57933].Rogue1 == 2 and src[57933].Rogue2 == 1 and src[10060].Priest == 1)
        ''')

    def test_buffs_up_at_the_pull_are_counted_once(self):
        self.check('''
        ROSTER = {"Hunter"}; BUFFS = {Hunter = {57933, 48470}}
        mode:CombatEnter()
        assert(pb(Skada.current, "Hunter") == 1 and pb(Skada.total, "Hunter") == 1)
        assert(Skada.current.actors.Hunter.powerbuffsources[57933].caster == 1)
        ''')


class DefaultsTests(unittest.TestCase):
    def test_lighter_defaults(self):
        import re
        opts = (ADDON / "Core/Options.lua").read_text(encoding="utf-8-sig")
        self.assertIn("updatefrequency = 1,", opts)
        blocked = opts[opts.index("modulesBlocked = {"):]
        blocked = blocked[:blocked.index("}")]
        self.assertIn('["Buffs"] = true', blocked)
        self.assertIn('["Debuffs"] = true', blocked)
        windefaults = opts[opts.index("Skada.windowdefaults = {"):opts.index("local windefaultscopy")]
        self.assertNotRegex(windefaults, r"smoothing\s*=\s*true")


class TankTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().TANK_SRC = (ADDON / "Modules/Tanks.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        M = {tanksonly = false}
        mode = load_module("Tanks", TANK_SRC, M)
        mode:OnEnable()
        Skada.current = {actors = {}}
        Skada.total = {actors = {}}
        heal_fn, hit_fn, aura_fn = CL[1].fn, CL[2].fn, CL[3].fn
        function heal(src, dst, amount, over)
          heal_fn(ev{event="SPELL_HEAL", spellid=1, srcGUID=src, dstGUID=dst, dstName=dst, dstFlags=1,
            amount=amount, overheal=over or 0})
        end
        function hit(dst, spell, amount, absorbed)
          hit_fn(ev{event="SPELL_DAMAGE", spellid=spell, srcGUID="boss", dstGUID=dst, dstName=dst, dstFlags=1,
            amount=amount, absorbed=absorbed})
        end
        function aura(event, dst, spell) aura_fn(ev{event=event, spellid=spell, dstGUID=dst}) end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_healing_from_others_and_own_are_split_without_overheal(self):
        self.check('''
        heal("Priest", "Tank", 1000, 300); heal("Tank", "Tank", 500)
        heal("Priest", "Tank", 200, 200)              -- pure overheal
        local a = Skada.current.actors.Tank
        assert(a.tankheal == 700 and a.tankself == 500)
        assert(Skada.total.actors.Tank.tankheal == 700)
        ''')

    def test_hits_count_active_cooldowns_and_bare_hits(self):
        self.check('''
        hit("Tank", 100, 5000)                        -- nothing up
        aura("SPELL_AURA_APPLIED", "Tank", 871)       -- Shield Wall
        aura("SPELL_AURA_APPLIED", "Tank", 33206)     -- Pain Suppression
        aura("SPELL_AURA_APPLIED", "Tank", 48470)     -- not a cooldown
        hit("Tank", 100, 2000, 500)
        aura("SPELL_AURA_REMOVED", "Tank", 33206)
        hit("Tank", 100, 3000)
        local s = Skada.current.actors.Tank.tankspells[100]
        assert(s.n == 3 and s.amount == 10500)
        assert(s.cd[0] == 1 and s.cd[871] == 2 and s.cd[33206] == 1 and not s.cd[48470])
        ''')

    def test_total_keeps_breakdown_only_for_tanks_and_custom_ids_work(self):
        self.check('''
        Skada.total.actors.Rogue = {role = "DAMAGER"}
        Skada.total.actors.Tank = {role = "TANK"}
        M.tankcustom = "71586, 99999"; mode:ApplySettings()
        aura("SPELL_AURA_APPLIED", "Tank", 71586)
        hit("Tank", 100, 10); hit("Rogue", 100, 10)
        assert(Skada.total.actors.Tank.tankspells[100].cd[71586] == 1)
        assert(not Skada.total.actors.Rogue.tankspells)
        assert(Skada.current.actors.Rogue.tankspells)
        ''')

    def test_shields_count_and_stance_marks_a_tank(self):
        self.check('''
        cbs = {}; Skada.RegisterCallback = function(_, e, fn) cbs[e] = fn end
        Skada.FindActor = function(_, set, name) return set.actors[name] end
        mode:OnEnable()
        heal("Priest", "Tank", 100)
        cbs.Skada_AbsorbLogged("Skada_AbsorbLogged", Skada.current, "Priest", "Tank", 400)
        cbs.Skada_AbsorbLogged("Skada_AbsorbLogged", Skada.current, "Tank", "Tank", 50)
        local a = Skada.current.actors.Tank
        assert(a.tankheal == 500 and a.tankself == 50)
        Skada.total.actors.Bear = {}
        aura_fn(ev{event="SPELL_AURA_APPLIED", spellid=9634, dstGUID="Bear", dstName="Bear", dstFlags=1})
        hit("Bear", 100, 10)
        assert(Skada.total.actors.Bear.tankstance and Skada.total.actors.Bear.tankspells)
        ''')

    def test_only_tanks_skips_other_players_before_any_lookup(self):
        self.check('''
        M.tanksonly = true
        Skada.GetUnitRole = function(guid) return guid == "Tank" and "TANK" or "NONE" end
        mode:OnEnable()
        ROSTER = {"Tank", "Mage", "Bear"}; BUFFS = {Bear = {9634}}
        mode:CombatEnter()
        local lookups = 0; local get = Skada.GetActor
        Skada.GetActor = function(...) lookups = lookups + 1; return get(...) end
        for i = 1, 100 do heal("Priest", "Mage", 10); hit("Mage", 100, 10) end
        assert(lookups == 0 and not Skada.current.actors.Mage)
        heal("Priest", "Tank", 10); hit("Bear", 100, 10)
        assert(Skada.current.actors.Tank.tankheal == 10 and Skada.current.actors.Bear.tankspells)
        hit_fn(ev{event="SPELL_MISSED", spellid=100, srcGUID="boss", dstGUID="Tank", dstName="Tank", dstFlags=1, amount=0, absorbed=900})
        hit_fn(ev{event="SWING_MISSED", spellid=6603, srcGUID="boss", dstGUID="Tank", dstName="Tank", dstFlags=1, amount=0})
        assert(Skada.current.actors.Tank.tankspells[100].amount == 900 and not Skada.current.actors.Tank.tankspells[6603])
        ''')

    def test_cooldown_up_at_the_pull_counts(self):
        self.check('''
        ROSTER = {"Tank"}; BUFFS = {Tank = {22812}}
        mode:CombatEnter()
        hit("Tank", 100, 10)
        assert(Skada.current.actors.Tank.tankspells[100].cd[22812] == 1)
        mode:CombatLeave(); hit("Tank", 100, 10)
        assert(Skada.current.actors.Tank.tankspells[100].cd[0] == 1)
        ''')


class MechanicTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().MECH_SRC = (ADDON / "Modules/Mechanics.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        NAMES = {[69674] = "Infection", [70337] = "Plague", [12345] = "Custom"}
        GetSpellInfo = function(i) return NAMES[i], nil, "icon" .. i end
        M = {}
        time = function() return 0 end
        UnitInVehicle = function(u) return SEATED and SEATED[u] end
        mode = load_module("Mechanics", MECH_SRC, M)
        M.mechuptime = true
        mode:OnEnable()
        Skada.current = {actors = {}}
        Skada.total = {actors = {}}
        aura_fn = CL[1].fn
        function aura(event, name, dst)
          aura_fn(ev{event=event, spellname=name, dstGUID=dst, dstName=dst, dstFlags=1})
        end
        function spell(set, dst, id) return set.actors[dst].mechspells[id] end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_counts_by_name_for_any_difficulty_and_times_until_removed(self):
        self.check('''
        NOW = 10; aura("SPELL_AURA_APPLIED", "Infection", "Mage")
        NOW = 14; aura("SPELL_AURA_REFRESH", "Infection", "Mage")   -- same debuff kept up
        NOW = 22; aura("SPELL_AURA_REMOVED", "Infection", "Mage")
        aura("SPELL_AURA_APPLIED", "Gift of the Wild", "Mage")
        local s = spell(Skada.current, "Mage", 69674)
        assert(s.n == 2 and s.t == 12 and Skada.current.actors.Mage.mech == 2)
        assert(spell(Skada.total, "Mage", 69674).t == 12)
        ''')

    def test_open_debuffs_close_at_combat_end(self):
        self.check('''
        NOW = 0; aura("SPELL_AURA_APPLIED", "Plague", "Tank")
        NOW = 30; mode:CombatLeave()
        assert(spell(Skada.current, "Tank", 70337).t == 30)
        NOW = 40; aura("SPELL_AURA_REMOVED", "Plague", "Tank")
        assert(spell(Skada.current, "Tank", 70337).t == 30)
        ''')

    def test_duration_off_keeps_counts_and_custom_ids_work(self):
        self.check('''
        M.mechuptime = false; M.mechcustom = "12345"; mode:ApplySettings()
        NOW = 0; aura("SPELL_AURA_APPLIED", "Custom", "Rogue")
        NOW = 9; aura("SPELL_AURA_REMOVED", "Custom", "Rogue")
        local s = spell(Skada.current, "Rogue", 12345)
        assert(s.n == 1 and not s.t)
        ''')

    def test_order_per_fight_and_total_keeps_counts_only(self):
        self.check('''
        Skada.current.starttime = 1000
        Skada._time = 1045; aura("SPELL_AURA_APPLIED", "Plague", "Tank")
        Skada._time = 1050; aura("SPELL_AURA_APPLIED", "Plague", "Mage")
        Skada._time = 1052; aura("SPELL_AURA_APPLIED", "Plague", "Tank")
        local o = Skada.current.mechorder[70337]
        assert(o.n[1] == "Tank" and o.n[2] == "Mage" and o.n[3] == "Tank")
        assert(o.t[1] == 45 and o.t[3] == 52)
        assert(not Skada.total.mechorder and spell(Skada.total, "Tank", 70337).n == 2)
        ''')

    def test_valkyr_grab_is_found_by_polling_and_counted_once_per_ride(self):
        self.check('''
        ROSTER = {"Mage", "Priest"}; SEATED = {}

        summon_fn = CL[2].fn
        summon_fn(ev{event="SPELL_SUMMON", spellid=69037})
        summon_fn(ev{event="SPELL_SUMMON", spellid=69037})    -- 2nd Val'kyr, same scan
        assert(#timers == 1)
        local function tick() local t = timers[#timers]; timers[#timers] = nil; t.fn() end
        tick()                                               -- nobody grabbed yet
        SEATED.Mage = true; tick(); tick()                   -- carried over two scans
        assert(spell(Skada.current, "Mage", 69037).n == 1)
        SEATED.Mage = nil; tick(); SEATED.Mage = true; tick() -- dropped and grabbed again
        assert(spell(Skada.current, "Mage", 69037).n == 2 and not Skada.current.actors.Priest)
        while #timers > 0 do tick() end                      -- the scan stops by itself
        ''')


class NoFlaskTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().POTIONS_SRC = (ADDON / "Modules/Potions.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        UnitIsConnected = function() return true end
        UnitIsDeadOrGhost = function(u) return u == "Dead" end
        UnitIsVisible = function(u) return u ~= "Far" end
        M = {}
        assert(loadstring(POTIONS_SRC))("Potions", Skada)
        ''')

    def test_players_without_flask_are_counted_per_pull_in_fight_and_total(self):
        self.lua.execute('''
        -- the registry keeps the last module: "No flask"; Potions still shares its flask ids.
        local reg = {}
        Skada.RegisterModule = function(_, name, fn) reg[name] = fn end
        assert(loadstring(POTIONS_SRC))("Potions", Skada)
        local O = {modules = {args = {}}, tweaks = {args = {general = {args = {}}}}}
        reg["Potions"](L, {}, {}, {}, {}, O)
        reg["No flask"](L, {}, {}, {}, M, O)
        local mode = Skada.modules["No flask"]
        mode.localeName = "No flask"; mode:OnInitialize()
        ROSTER = {"Mage", "Rogue", "Dead", "Far"}
        BUFFS = {Mage = {53758}}                     -- Mage has a flask
        Skada.total = {actors = {}}
        for pull = 1, 2 do
          Skada.current = {actors = {}}
          mode:CombatEnter(); mode:CombatLeave()
          assert(Skada.current.actors.Rogue.noflask == 1 and not Skada.current.actors.Mage)
          assert(not Skada.current.actors.Dead and not Skada.current.actors.Far)
        end
        assert(Skada.total.actors.Rogue.noflask == 2 and Skada.total.noflask == 2)
        ''')


class DeathSavesTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(SETUP)
        self.lua.globals().DEATHS_SRC = (ADDON / "Modules/Deaths.lua").read_text(encoding="utf-8-sig")
        self.lua.execute('''
        Skada.Private.tremove = table.remove
        Skada.Private.guidToUnit = {}
        Skada.UnitHealthInfo = function() return 0, 1000, 1000 end
        Skada.ignored_spells = {damage = {}}
        Skada.ress_spells = {}
        Skada.IsInGroup = function() return true end
        Skada.IsInPvP = function() return false end
        UnitIsFeignDeath = function() return false end
        date = os.date; time = function() return NOW end
        M = {deathready = true, deathlogevents = 14, deathlogthreshold = 1000}
        mode = load_module("Deaths", DEATHS_SRC, M)
        mode:OnEnable()
        Skada.current = {actors = {}}
        function fn_for(event, nth)
          local k = 0
          for i = 1, #CL do for _, e in ipairs(CL[i].events) do
            if e == event then k = k + 1; if k == (nth or 1) then return CL[i].fn end end
          end end
        end
        function hit(name) fn_for("SPELL_DAMAGE")(ev{event="SPELL_DAMAGE", spellid=1, spellstring="1",
          amount=5000, srcName="Boss", dstGUID="g"..name, dstName=name, dstFlags=1}) end
        function die(name) fn_for("UNIT_DIED")(ev{event="UNIT_DIED", dstGUID="g"..name, dstName=name, dstFlags=1}) end
        function cast(name, id) fn_for("SPELL_CAST_SUCCESS", 2)(ev{event="SPELL_CAST_SUCCESS", spellid=id, srcName=name}) end
        function lock(event, name, id) fn_for("SPELL_AURA_APPLIED", 4)(ev{event=event, spellid=id, dstName=name}) end
        function ready(name) return Skada.current.actors[name].deathlog[1].ready end
        ''')

    def test_ready_saves_are_listed_and_cooldowns_and_lockouts_respected(self):
        self.lua.execute('''
        NOW = 0; cast("Mage", 45438); cast("Pala", 642); cast("Pala", 498)
        NOW = 200; hit("Mage"); die("Mage")
        assert(not ready("Mage"))                                  -- Ice Block still on cooldown
        NOW = 400; lock("SPELL_AURA_APPLIED", "Pala", 25771)        -- Forbearance
        hit("Pala"); die("Pala")
        assert(not ready("Pala"))
        lock("SPELL_AURA_REMOVED", "Pala", 25771)
        Skada.current = {actors = {}}
        hit("Pala"); die("Pala"); hit("Mage"); die("Mage"); hit("Rogue"); die("Rogue")
        local r = ready("Pala")
        assert(r[1] == 498 and r[2] == 642 and ready("Mage")[1] == 45438)
        assert(not ready("Rogue"))                                  -- never seen pressing a save
        M.deathready = false; Skada.current = {actors = {}}
        hit("Pala"); die("Pala"); assert(not ready("Pala"))
        ''')


if __name__ == "__main__":
    unittest.main()
