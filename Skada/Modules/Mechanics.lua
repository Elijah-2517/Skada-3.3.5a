local _, Skada = ...
local Private = Skada.Private
Skada:RegisterModule("Mechanics", function(L, P, _, _, M, O)
	local mode = Skada:NewModule("Mechanics")
	local mode_spell = mode:NewModule("Spell List")
	local mode_target = mode_spell:NewModule("Target List")

	local pairs, format, tonumber, gmatch = pairs, string.format, tonumber, string.gmatch
	local GetSpellInfo, GetTime = GetSpellInfo, GetTime
	local classfmt = Skada.classcolors.format
	local mode_cols = nil

	-- boss mechanics landing on players. Matched by name: 10/25 and heroic use other ids.
	local builtin = {
		69065, -- Marrowgar: Impale
		71289, 71237, -- Deathwhisper: Dominate Mind, Curse of Torpor
		72293, 72385, 72410, -- Saurfang: Mark of the Fallen Champion, Boiling Blood, Rune of Blood
		69279, 69240, 72219, -- Festergut: Gas Spore, Vile Gas, Gastric Bloat
		69674, -- Rotface: Mutated Infection
		70911, 70672, 70447, 72451, -- Putricide: Unbound Plague, Gaseous Bloat, Volatile Ooze Adhesive, Mutated Plague
		72999, -- Blood Princes: Shadow Prison
		70867, 71340, 71264, 70923, -- Lana'thel: Essence, Pact of the Darkfallen, Swarming Shadows, Uncontrollable Frenzy
		70126, 69762, 69766, 70106, 70128, 70157, -- Sindragosa: Frost Beacon, Unchained Magic, Instability, Chilled to the Bone, Mystic Buffet, Ice Tomb
		70337, 68980, 69409, 70541, 72743, -- Lich King: Necrotic Plague, Harvest Soul, Soul Reaper, Infest, Defile
		74562, 74792 -- Halion: Fiery Combustion, Soul Consumption
	}
	local names = {} -- [localized name] = spell id used for the icon
	local custom_cache
	local started = {} -- [guid] = {[spellid] = {t = start, name = , flags = }}

	local function refresh_names()
		if custom_cache == (M.mechcustom or "") then return end
		custom_cache = M.mechcustom or ""
		Private.clearTable(names)
		local function add(id)
			local name = id and GetSpellInfo(id)
			if name and not names[name] then names[name] = id end
		end
		for i = 1, #builtin do add(builtin[i]) end
		for id in gmatch(custom_cache, "%d+") do add(tonumber(id)) end
	end

	local function get_spell(set, name, guid, flags, spellid)
		local actor = Skada:GetActor(set, name, guid, flags)
		if not actor then return end
		actor.mechspells = actor.mechspells or {}
		local spell = actor.mechspells[spellid]
		if not spell then
			spell = {n = 0}
			actor.mechspells[spellid] = spell
		end
		return actor, spell
	end

	local function log_applied(set, name, guid, flags, spellid)
		local actor, spell = get_spell(set, name, guid, flags, spellid)
		if not actor then return end
		spell.n = spell.n + 1
		actor.mech = (actor.mech or 0) + 1
		set.mech = (set.mech or 0) + 1
	end

	-- shortcut: a phase segment opened mid-debuff gets the whole duration, fine for a debuff view.
	local function log_time(set, name, guid, flags, spellid, duration)
		local _, spell = get_spell(set, name, guid, flags, spellid)
		if spell then spell.t = (spell.t or 0) + duration end
	end

	local function stop_timer(guid, spellid, now)
		local list = started[guid]
		local timer = list and list[spellid]
		if not timer then return end
		list[spellid] = nil
		local duration = now - timer.t
		if duration > 0 then
			Skada:DispatchSets(log_time, timer.name, guid, timer.flags, spellid, duration)
		end
	end

	local function aura(t)
		local spellid = t.spellname and names[t.spellname]
		if not spellid or not t.dstGUID then return end

		if t.event == "SPELL_AURA_REMOVED" then
			if M.mechuptime then stop_timer(t.dstGUID, spellid, GetTime()) end
			return
		end

		Skada:DispatchSets(log_applied, t.dstName, t.dstGUID, t.dstFlags, spellid)
		if M.mechuptime then
			local list = started[t.dstGUID] or {}
			started[t.dstGUID] = list
			-- a refresh keeps the debuff up, so its time keeps running.
			list[spellid] = list[spellid] or {t = GetTime(), name = t.dstName, flags = t.dstFlags}
		end
	end

	-- debuffs still up when the fight ends count until that moment.
	function mode:CombatLeave()
		local now = GetTime()
		for guid, list in pairs(started) do
			for spellid in pairs(list) do stop_timer(guid, spellid, now) end
		end
		Private.clearTable(started)
	end

	local function valuetext(d, count, duration)
		d.valuetext = Skada:FormatValueCols(
			mode_cols.Count and count,
			M.mechuptime and mode_cols.Uptime and duration and Skada:FormatTime(duration)
		)
	end

	function mode_target:Enter(win, id, label)
		win.spellid, win.spellname = id, label
		win.title = format(L["%s's targets"], label)
	end

	function mode_target:Update(win, set)
		win.title = format(L["%s's targets"], win.spellname or L["Unknown"])
		if not set or not set.actors or not win.spellid then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for actorname, actor in pairs(set.actors) do
			local spell = actor.mechspells and actor.mechspells[win.spellid]
			if spell and win:show_actor(actor, set, true) then
				nr = nr + 1
				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = spell.n
				valuetext(d, spell.n, spell.t)
				if win.metadata and d.value > win.metadata.maxvalue then win.metadata.maxvalue = d.value end
			end
		end
	end

	function mode_spell:Enter(win, id, label, class)
		win.actorid, win.actorname, win.actorclass = id, label, class
		win.title = format(L["%s's mechanics"], classfmt(class, label))
	end

	function mode_spell:Update(win, set)
		win.title = format(L["%s's mechanics"], classfmt(win.actorclass, win.actorname))
		if not set or not win.actorname then return end

		local actor = Skada:FindActor(set, win.actorname, win.actorid, true)
		local spells = actor and actor.mechspells
		if not spells then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for spellid, spell in pairs(spells) do
			local name, _, icon = GetSpellInfo(spellid)
			nr = nr + 1
			local d = win:nr(nr)
			d.id = spellid
			d.spellid = spellid
			d.label = name or L["Unknown"]
			d.icon = icon
			d.value = spell.n
			valuetext(d, spell.n, spell.t)
			if win.metadata and d.value > win.metadata.maxvalue then win.metadata.maxvalue = d.value end
		end
	end

	function mode:Update(win, set)
		win.title = win.class and format("%s (%s)", L["Mechanics"], L[win.class]) or L["Mechanics"]
		local total = set and set:GetTotal(win.class, nil, "mech")
		if not total or total == 0 then return end
		if win.metadata then win.metadata.maxvalue = 0 end

		local nr = 0
		for actorname, actor in pairs(set.actors) do
			if actor.mech and win:show_actor(actor, set, true) then
				local duration
				for _, spell in pairs(actor.mechspells or Skada.dummyTable) do
					if spell.t then duration = (duration or 0) + spell.t end
				end
				nr = nr + 1
				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = actor.mech
				valuetext(d, actor.mech, duration)
				if win.metadata and d.value > win.metadata.maxvalue then win.metadata.maxvalue = d.value end
			end
		end
	end

	function mode:GetSetSummary(set, win)
		return set and set:GetTotal(win and win.class, nil, "mech") or 0
	end

	function mode:ApplySettings()
		refresh_names()
		if not M.mechuptime then Private.clearTable(started) end
	end

	function mode:OnEnable()
		mode_target.metadata = {}
		mode_spell.metadata = {click1 = mode_target}
		self.metadata = {
			showspots = true,
			ordersort = true,
			filterclass = true,
			click1 = mode_spell,
			columns = {Count = true, Uptime = true},
			icon = [[Interface\ICONS\spell_shadow_plaguecloud]]
		}
		mode_cols = self.metadata.columns
		refresh_names()

		Skada:RegisterForCL(aura, {dst_is_interesting_nopets = true},
			"SPELL_AURA_APPLIED", "SPELL_AURA_REFRESH", "SPELL_AURA_REMOVED")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_LEAVE", "CombatLeave")
		Skada.RegisterCallback(self, "Skada_ApplySettings", "ApplySettings")
		Skada:AddMode(self, "Buffs and Debuffs")
	end

	function mode:OnDisable()
		Skada:UnregisterFromCL(aura)
		Skada.UnregisterAllMessages(self)
		Skada.UnregisterAllCallbacks(self)
		Skada:RemoveMode(self)
	end

	function mode:OnInitialize()
		if M.mechuptime == nil then M.mechuptime = true end

		O.modules.args.mechanics = {
			type = "group",
			name = self.localeName,
			desc = format(L["Options for %s."], self.localeName),
			args = {
				header = {
					type = "description",
					name = self.localeName,
					fontSize = "large",
					image = [[Interface\ICONS\spell_shadow_plaguecloud]],
					imageWidth = 18,
					imageHeight = 18,
					imageCoords = Skada.cropTable,
					width = "full",
					order = 0
				},
				mechuptime = {
					type = "toggle",
					name = L["Track duration"],
					desc = L["opt_mechuptime_desc"],
					descStyle = "inline",
					width = "full",
					order = 10
				},
				mechcustom = {
					type = "input",
					name = L["Extra mechanics"],
					desc = L["opt_mechcustom_desc"],
					width = "full",
					order = 20
				}
			}
		}
	end
end)
