local _, Skada = ...
local Private = Skada.Private
Skada:RegisterModule("Tanks", function(L, P, _, _, M, O)
	local mode = Skada:NewModule("Tanks")
	local mode_spell = mode:NewModule("Spell List")
	local mode_cd = mode_spell:NewModule("Cooldowns")

	local pairs, format, tonumber, gmatch = pairs, string.format, tonumber, string.gmatch
	local UnitGUID, UnitName, UnitBuff = UnitGUID, UnitName, UnitBuff
	local SpellInfo = Private.SpellInfo or GetSpellInfo
	local classfmt = Skada.classcolors.format
	local mode_cols = nil

	-- defensive buffs seen on the target when a hit lands (3.3.5a ids).
	local builtin = {
		871, 12976, 2565, 55694, 23920, -- warrior
		48792, 55233, 49222, 51271, 48707, 50461, 49039, -- death knight
		22812, 61336, 22842, -- druid
		498, 642, 1022, 5599, 10278, 6940, 64205, 70940, 31821, -- paladin
		33206, 47788, -- priest
		5277, 26669, 31224, 45438, 19263, 47585, 30823, -- others
		53762, -- Indestructible Potion
		71586, 71638 -- Corroded Skeleton Key, Sindragosa's Flawless Fang
	}
	-- stances and forms only a tank keeps up, for players whose talents were not read yet.
	local stances = {[71] = true, [48263] = true, [5487] = true, [9634] = true, [25780] = true}
	local cooldowns = {}
	local custom_cache
	local active = {} -- [guid] = {[spellid] = true}
	local tanks = {} -- [guid] = true, rebuilt each pull

	-- with "Only tanks" the other 20+ players are skipped before any set lookup.
	local function tracked(guid)
		return not M.tanksonly or tanks[guid]
	end

	local function refresh_cooldowns()
		if custom_cache == (M.tankcustom or "") then return end
		custom_cache = M.tankcustom or ""
		Private.clearTable(cooldowns)
		for i = 1, #builtin do cooldowns[builtin[i]] = true end
		for id in gmatch(custom_cache, "%d+") do cooldowns[tonumber(id)] = true end
	end

	local function is_tank(actor)
		return actor.role == "TANK" or actor.tankstance
	end

	local function shown(actor)
		return not M.tanksonly or is_tank(actor)
	end

	local function mark_tank(set, name, guid, flags)
		local actor = Skada:GetActor(set, name, guid, flags)
		if actor then actor.tankstance = true end
	end

	local function log_heal(set, name, guid, flags, amount, own)
		local actor = Skada:GetActor(set, name, guid, flags)
		if not actor then return end
		local key = own and "tankself" or "tankheal"
		actor[key] = (actor[key] or 0) + amount
		set[key] = (set[key] or 0) + amount
	end

	local function spell_heal(t)
		local amount = (t.amount or 0) - (t.overheal or 0)
		if amount <= 0 or not t.dstGUID or not tracked(t.dstGUID) then return end
		Skada:DispatchSets(log_heal, t.dstName, t.dstGUID, t.dstFlags, amount, t.srcGUID == t.dstGUID)
	end

	local function log_hit(set, name, guid, flags, spellid, amount, buffs)
		local actor = Skada:GetActor(set, name, guid, flags)
		if not actor then return end
		-- saving this to total set may become a memory hog deluxe.
		if set == Skada.total and not P.totalidc and not is_tank(actor) then return end

		actor.tankspells = actor.tankspells or {}
		local spell = actor.tankspells[spellid]
		if not spell then
			spell = {n = 0, amount = 0, cd = {}}
			actor.tankspells[spellid] = spell
		end
		spell.n = spell.n + 1
		spell.amount = spell.amount + amount

		local none = true
		for cd in pairs(buffs or Skada.dummyTable) do
			spell.cd[cd] = (spell.cd[cd] or 0) + 1
			none = false
		end
		if none then spell.cd[0] = (spell.cd[0] or 0) + 1 end
	end

	local function spell_damage(t)
		if not t.spellid or not t.dstGUID or t.srcGUID == t.dstGUID or not tracked(t.dstGUID) then return end
		local amount = (t.amount or 0) + (t.absorbed or 0)
		if amount <= 0 then return end
		Skada:DispatchSets(log_hit, t.dstName, t.dstGUID, t.dstFlags, t.spellid, amount, active[t.dstGUID])
	end

	-- shields from the Absorbs module count as healing: they save the healers the same work.
	local function absorb_logged(_, set, srcGUID, dstName, amount)
		local actor = set and dstName and amount and amount > 0 and Skada:FindActor(set, dstName)
		if not actor or not tracked(actor.id) then return end
		local key = actor.id == srcGUID and "tankself" or "tankheal"
		actor[key] = (actor[key] or 0) + amount
		set[key] = (set[key] or 0) + amount
	end

	local function aura(t)
		if not t.spellid or not t.dstGUID then return end
		if stances[t.spellid] and t.event ~= "SPELL_AURA_REMOVED" then
			tanks[t.dstGUID] = true
			Skada:DispatchSets(mark_tank, t.dstName, t.dstGUID, t.dstFlags)
		end
		if not cooldowns[t.spellid] then return end
		local buffs = active[t.dstGUID]
		if t.event == "SPELL_AURA_REMOVED" then
			if buffs then buffs[t.spellid] = nil end
		else
			buffs = buffs or {}
			buffs[t.spellid] = true
			active[t.dstGUID] = buffs
		end
	end

	local function format_valuetext(d, col1, col2, col3)
		d.valuetext = Skada:FormatValueCols(col1, col2, col3)
	end

	function mode_cd:Enter(win, id, label)
		win.spellid, win.spellname = id, label
		win.title = format(L["Cooldowns on %s"], label)
	end

	function mode_cd:Update(win, set)
		win.title = format(L["Cooldowns on %s"], win.spellname or L["Unknown"])
		if not set or not win.actorname or not win.spellid then return end

		local actor = Skada:FindActor(set, win.actorname, win.actorid, true)
		local spell = actor and actor.tankspells and actor.tankspells[win.spellid]
		if not spell or spell.n == 0 then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for cd, count in pairs(spell.cd) do
			nr = nr + 1
			local d = win:nr(nr)
			d.id = cd
			if cd == 0 then
				d.label = L["No cooldowns"]
				d.icon = [[Interface\ICONS\inv_misc_questionmark]]
			else
				local name, _, icon = SpellInfo(cd)
				d.spellid = cd
				d.label = name or L["Unknown"]
				d.icon = icon
			end
			d.value = count
			format_valuetext(d, mode_cols.Count and count, mode_cols.sPercent and Skada:FormatPercent(count, spell.n))
			if win.metadata and count > win.metadata.maxvalue then win.metadata.maxvalue = count end
		end
	end

	function mode_spell:Enter(win, id, label, class)
		win.actorid, win.actorname, win.actorclass = id, label, class
		win.title = format(L["%s's hits taken"], classfmt(class, label))
	end

	function mode_spell:Update(win, set)
		win.title = format(L["%s's hits taken"], classfmt(win.actorclass, win.actorname))
		if not set or not win.actorname then return end

		local actor = Skada:FindActor(set, win.actorname, win.actorid, true)
		local spells = actor and actor.tankspells
		if not spells then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for spellid, spell in pairs(spells) do
			nr = nr + 1
			local d = win:nr(nr)
			local name, _, icon = SpellInfo(spellid)
			d.id = spellid
			d.spellid = spellid
			d.label = name or L["Unknown"]
			d.icon = icon
			d.value = spell.n
			format_valuetext(d,
				mode_cols.Count and spell.n,
				mode_cols.Damage and Skada:FormatNumber(spell.amount),
				mode_cols.Covered and Skada:FormatPercent(spell.n - (spell.cd[0] or 0), spell.n)
			)
			if win.metadata and spell.n > win.metadata.maxvalue then win.metadata.maxvalue = spell.n end
		end
	end

	function mode:Update(win, set)
		win.title = win.class and format("%s (%s)", L["Tanks"], L[win.class]) or L["Tanks"]
		if not set or not set.actors then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for actorname, actor in pairs(set.actors) do
			if (actor.tankheal or actor.tankself or actor.tankspells) and shown(actor) and win:show_actor(actor, set, true) then
				nr = nr + 1
				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = actor.tankheal or 0
				format_valuetext(d,
					mode_cols.Healing and Skada:FormatNumber(d.value),
					mode_cols.Own and Skada:FormatNumber(actor.tankself or 0)
				)
				if win.metadata and d.value > win.metadata.maxvalue then win.metadata.maxvalue = d.value end
			end
		end
	end

	function mode:GetSetSummary(set)
		return set and set.tankheal or 0
	end

	-- buffs used right before the pull are already up when combat starts.
	function mode:CombatEnter()
		Private.clearTable(active)
		Private.clearTable(tanks)
		local GetUnitRole = Skada.GetUnitRole
		for unit in Skada.UnitIterator(true) do
			local guid = UnitGUID(unit)
			local tank = (guid and GetUnitRole and GetUnitRole(guid) == "TANK") or (GetPartyAssignment and GetPartyAssignment("MAINTANK", unit))
			for i = 1, 40 do
				local name, _, _, _, _, _, _, _, _, _, spellid = UnitBuff(unit, i)
				if not name then break end
				if guid and cooldowns[spellid] then
					active[guid] = active[guid] or {}
					active[guid][spellid] = true
				end
				tank = tank or stances[spellid]
			end
			if guid and tank then
				tanks[guid] = true
				local fullname = Private.UnitFullname and Private.UnitFullname(unit) or UnitName(unit)
				Skada:DispatchSets(mark_tank, fullname, guid, Private.DEFAULT_FLAGS)
			end
		end
	end

	function mode:CombatLeave()
		Private.clearTable(active)
	end

	function mode:ApplySettings()
		refresh_cooldowns()
	end

	function mode:OnEnable()
		mode_cd.metadata = {}
		mode_spell.metadata = {click1 = mode_cd}
		self.metadata = {
			showspots = true,
			filterclass = true,
			click1 = mode_spell,
			columns = {Healing = true, Own = true, Count = true, Damage = true, Covered = true, sPercent = true},
			icon = [[Interface\ICONS\ability_warrior_shieldwall]]
		}
		mode_cols = self.metadata.columns
		refresh_cooldowns()

		local flags_dst = {dst_is_interesting_nopets = true}
		Skada:RegisterForCL(spell_heal, flags_dst, "SPELL_HEAL", "SPELL_PERIODIC_HEAL")
		Skada:RegisterForCL(spell_damage, flags_dst,
			"SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "SPELL_BUILDING_DAMAGE", "RANGE_DAMAGE", "SWING_DAMAGE",
			-- a hit fully eaten by a shield arrives as a miss with the absorbed amount
			"SPELL_MISSED", "SPELL_PERIODIC_MISSED", "RANGE_MISSED", "SWING_MISSED")
		Skada:RegisterForCL(aura, flags_dst, "SPELL_AURA_APPLIED", "SPELL_AURA_REFRESH", "SPELL_AURA_REMOVED")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_ENTER", "CombatEnter")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_LEAVE", "CombatLeave")
		Skada.RegisterCallback(self, "Skada_ApplySettings", "ApplySettings")
		Skada.RegisterCallback(self, "Skada_AbsorbLogged", absorb_logged)
		Skada:AddMode(self, "Damage Taken")
	end

	function mode:OnDisable()
		Skada:UnregisterFromCL(spell_heal)
		Skada:UnregisterFromCL(spell_damage)
		Skada:UnregisterFromCL(aura)
		Skada.UnregisterAllMessages(self)
		Skada.UnregisterAllCallbacks(self)
		Skada:RemoveMode(self)
	end

	function mode:OnInitialize()
		if M.tanksonly == nil then M.tanksonly = true end

		O.modules.args.tanks = {
			type = "group",
			name = self.localeName,
			desc = format(L["Options for %s."], self.localeName),
			args = {
				header = {
					type = "description",
					name = self.localeName,
					fontSize = "large",
					image = [[Interface\ICONS\ability_warrior_shieldwall]],
					imageWidth = 18,
					imageHeight = 18,
					imageCoords = Skada.cropTable,
					width = "full",
					order = 0
				},
				tanksonly = {
					type = "toggle",
					name = L["Only tanks"],
					desc = L["opt_tanksonly_desc"],
					descStyle = "inline",
					width = "full",
					order = 10
				},
				tankcustom = {
					type = "input",
					name = L["Extra cooldowns"],
					desc = L["opt_tankcustom_desc"],
					width = "full",
					order = 20
				}
			}
		}
	end
end)
