local _, Skada = ...
local Private = Skada.Private
Skada:RegisterModule("Sunder Counter", function(L, P, _, C, M, O)
	local mode = Skada:NewModule("Sunder Counter")
	local mode_target = mode:NewModule("Target List")
	local mode_target_source = mode_target:NewModule("Source List")
	local get_actor_sunder_sources = nil
	local get_actor_sunder_targets = nil

	local pairs, format, GetTime, uformat = pairs, string.format, GetTime, Private.uformat
	local new, del, clear = Private.newTable, Private.delTable, Private.clearTable
	local SpellLink = Private.SpellLink or GetSpellLink
	local classfmt = Skada.classcolors.format
	local spellnames = Skada.spellnames

	local sunder_targets -- holds sunder targets details for announcement
	local sunder_timers -- holds scheduled sunder drop timers
	local active_sunders = {} -- holds sunder targets to consider refreshes
	local spell_sunder, sunder_link
	local armor_spells = {
		[7386] = 47467, [7405] = 47467, [8380] = 47467, [11596] = 47467,
		[11597] = 47467, [25225] = 47467, [47467] = 47467,
		[8647] = 8647, [8649] = 8647, [8650] = 8647, [11197] = 8647,
		[11198] = 8647, [26866] = 8647, [48669] = 8647,
		[64382] = 64382
	}
	local mode_cols = nil

	local function format_valuetext(d, total, metadata, subview)
		d.valuetext = Skada:FormatValueCols(
			mode_cols.Count and Skada:FormatNumber(d.value),
			mode_cols[subview and "sPercent" or "Percent"] and Skada:FormatPercent(d.value, total)
		)

		if metadata and d.value > metadata.maxvalue then
			metadata.maxvalue = d.value
		end
	end

	local function log_sunder(set, actorname, actorid, actorflags, dstName, spellid)
		local actor = Skada:GetActor(set, actorname, actorid, actorflags)
		if not actor then return end

		set.sunder = (set.sunder or 0) + 1
		actor.sunder = (actor.sunder or 0) + 1
		actor.sunderspells = actor.sunderspells or {}
		actor.sunderspells[spellid] = (actor.sunderspells[spellid] or 0) + 1

		-- saving this to total set may become a memory hog deluxe.
		if (set == Skada.total and not P.totalidc) or not dstName then return end

		actor.sundertargets = actor.sundertargets or {}
		actor.sundertargets[dstName] = (actor.sundertargets[dstName] or 0) + 1
	end

	local function sunder_dropped(dstGUID)
		if not dstGUID then return end

		-- announce drop...
		if sunder_targets and sunder_targets[dstGUID] then
			local dstName = sunder_targets[dstGUID].name
			sunder_targets[dstGUID] = del(sunder_targets[dstGUID])
			mode:Announce(uformat(L["%s dropped from %s!"], sunder_link or spell_sunder, dstName))
		end

		-- cancel drop timer...
		if sunder_timers and sunder_timers[dstGUID] then
			Skada:CancelTimer(sunder_timers[dstGUID], true)
			sunder_timers[dstGUID] = nil

			if not next(sunder_timers) then
				sunder_timers = del(sunder_timers)
			end
		end
	end

	local function sunder_applied(t)
		local spellid = armor_spells[t.spellid]
		if not spellid or not t.dstGUID then return end

		if t.event == "SPELL_AURA_REMOVED" then
			if spellid == 47467 then
				active_sunders[t.dstGUID] = nil
				if sunder_timers and sunder_timers[t.dstGUID] then Skada:CancelTimer(sunder_timers[t.dstGUID], true) end
				sunder_timers = sunder_timers or new()
				sunder_timers[t.dstGUID] = Skada:ScheduleTimer(sunder_dropped, 0.1, t.dstGUID)
			end
			return
		end
		if not t.srcGUID or not t.srcName then return end

		local curtime = Skada._Time or GetTime()
		if spellid == 47467 then
			if sunder_timers and sunder_timers[t.dstGUID] then
				Skada:CancelTimer(sunder_timers[t.dstGUID], true)
				sunder_timers[t.dstGUID] = nil
			end
			if t.event == "SPELL_AURA_REFRESH" and active_sunders[t.dstGUID] and active_sunders[t.dstGUID] > curtime then
				active_sunders[t.dstGUID] = curtime + M.sunderdelay
				return
			end
			active_sunders[t.dstGUID] = curtime + M.sunderdelay
		end

		-- Aura events identify the actual caster, including Sunder applied by Devastate.
		Skada:DispatchSets(log_sunder, t.srcName, t.srcGUID, t.srcFlags, t.dstName, spellid)
		if spellid ~= 47467 then return end

		-- announce disabled or only for bosses
		if not M.sunderannounce or (M.sunderbossonly and not t:DestIsBoss()) then return end

		local tar = sunder_targets and sunder_targets[t.dstGUID]
		if not tar then
			tar = new()
			tar.name = t.dstName
			tar.count = t.amount or 1
			tar.time = curtime
			sunder_targets = sunder_targets or {}
			sunder_targets[t.dstGUID] = tar
		elseif not tar.full then
			tar.count = t.amount or (t.event == "SPELL_AURA_APPLIED_DOSE" and ((tar.count or 0) + 1)) or tar.count
			if tar.count == 5 then
				mode:Announce(format(
					L["%s stacks of %s applied on %s in %s sec!"],
					tar.count,
					sunder_link or spell_sunder,
					t.dstName,
					format("%.1f", curtime - tar.time)
				))
				tar.full = true
			end
		end
	end

	local function unit_died(t)
		active_sunders[t.dstGUID] = nil
		if sunder_timers and sunder_timers[t.dstGUID] then
			Skada:CancelTimer(sunder_timers[t.dstGUID], true)
			sunder_timers[t.dstGUID] = nil
		end
		if sunder_targets and t.dstGUID and sunder_targets[t.dstGUID] then
			sunder_targets[t.dstGUID] = del(sunder_targets[t.dstGUID])
		end
	end

	local function double_check_sunder()
		if not spell_sunder then
			spell_sunder = spellnames[47467]
		end
		if not sunder_link then
			sunder_link = SpellLink(47467)
		end
	end

	function mode_target_source:Enter(win, id, label, class)
		win.targetid, win.targetname, win.targetclass = id, label, class
		win.title = format(L["%s's sources"], classfmt(class, label))
	end

	function mode_target_source:Update(win, set)
		win.title = uformat(L["%s's sources"], classfmt(win.targetclass, win.targetname))
		if not win.targetname then return end

		local sources, total = get_actor_sunder_sources(set, win.targetname)
		if not sources or total == 0 then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for sourcename, source in pairs(sources) do
			nr = nr + 1

			local d = win:actor(nr, source, source.enemy, sourcename)
			d.value = source.count
			format_valuetext(d, total, win.metadata, true)
		end
	end

	function mode_target:Enter(win, id, label, class)
		win.actorid, win.actorname, win.actorclass = id, label, class
		win.title = format(L["%s's targets"], classfmt(class, label))
	end

	function mode_target:Update(win, set)
		double_check_sunder()
		win.title = uformat(L["%s's targets"], classfmt(win.actorclass, win.actorname))
		if not set or not win.actorname then return end

		local targets, total, actor = get_actor_sunder_targets(set, win.actorname, win.actorid)
		if not targets or not actor or total == 0 then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for targetname, target in pairs(targets) do
			nr = nr + 1

			local d = win:actor(nr, target, target.enemy, targetname)
			d.value = target.count
			format_valuetext(d, total, win.metadata, true)
		end
	end

	function mode:Update(win, set)
		double_check_sunder()
		win.title = L["Sunder Counter"]

		local total = set.sunder
		if not total or total == 0 then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		local actors = set.actors

		for actorname, actor in pairs(actors) do
			if actor and actor.sunder then
				nr = nr + 1

				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = actor.sunder
				format_valuetext(d, total, win.metadata)
			end
		end
	end

	function mode_target:GetSetSummary(set, win)
		local actor = set and win and set:GetActor(win.actorname, win.actorid)
		return actor and actor.sunder
	end

	function mode:GetSetSummary(set)
		return set and set.sunder
	end

	function mode:AddToTooltip(set, tooltip)
		if set.sunder and set.sunder > 0 then
			tooltip:AddDoubleLine(spell_sunder, set.sunder, 1, 1, 1)
		end
	end

	local function armor_tooltip(win, id, label, tooltip)
		local set = win:GetSelectedSet()
		local actor = set and set:GetActor(label, id)
		if not actor or not actor.sunderspells then return end
		for spellid, count in pairs(actor.sunderspells) do
			tooltip:AddDoubleLine(spellnames[spellid], count, 1, 1, 1)
		end
	end

	function mode:OnEnable()
		mode_target_source.metadata = {showspots = true}
		mode_target.metadata = {click1 = mode_target_source}
		self.metadata = {
			showspots = true,
			click1 = mode_target,
			tooltip = armor_tooltip,
			columns = {Count = true, Percent = false, sPercent = false},
			icon = [[Interface\ICONS\ability_warrior_sunder]]
		}

		mode_cols = self.metadata.columns

		-- no total click.
		mode_target.nototal = true

		local flags_src = {src_is_interesting_nopets = true}
		Skada:RegisterForCL(
			sunder_applied,
			flags_src,
			"SPELL_AURA_APPLIED",
			"SPELL_AURA_APPLIED_DOSE",
			"SPELL_AURA_REFRESH",
			"SPELL_AURA_REMOVED"
		)

		Skada:RegisterForCL(
			unit_died,
			{dst_is_not_interesting = true},
			"UNIT_DIED",
			"UNIT_DESTROYED",
			"UNIT_DISSIPATES"
		)

		Skada.RegisterMessage(self, "COMBAT_PLAYER_LEAVE", "CombatLeave")
		Skada.RegisterCallback(self, "Skada_DataReset", "CombatLeave")
		Skada:AddMode(self, "Buffs and Debuffs")
	end

	function mode:OnDisable()
		self:CombatLeave()
		Skada:UnregisterFromCL(sunder_applied)
		Skada:UnregisterFromCL(unit_died)
		Skada.UnregisterAllMessages(self)
		Skada.UnregisterAllCallbacks(self)
		Skada:RemoveMode(self)
	end

	function mode:CombatLeave()
		clear(sunder_targets)
		clear(active_sunders)
		for _, timer in pairs(sunder_timers or Skada.dummyTable) do Skada:CancelTimer(timer, true) end
		if sunder_timers then sunder_timers = del(sunder_timers) end
	end

	function mode:Announce(msg)
		Skada:SendChat(msg, M.sunderchannel or "SAY", "preset")
	end

	function mode:OnInitialize()
		double_check_sunder()

		M.sunderchannel = M.sunderchannel or "SAY"
		M.sunderdelay = M.sunderdelay or 20

		O.modules.args.sundercounter = {
			type = "group",
			name = self.localeName,
			desc = format(L["Options for %s."], self.localeName),
			args = {
				header = {
					type = "description",
					name = self.localeName,
					fontSize = "large",
					image = [[Interface\ICONS\ability_warrior_sunder]],
					imageWidth = 18,
					imageHeight = 18,
					imageCoords = Skada.cropTable,
					width = "full",
					order = 0
				},
				empty_1 = {
					type = "description",
					name = " ",
					width = "full",
					order = 1
				},
				sunderannounce = {
					type = "toggle",
					name = format(L["Announce %s"], spell_sunder),
					desc = uformat(L["Announces how long it took to apply %d stacks of %s and announces when it drops."], 5, spell_sunder),
					descStyle = "inline",
					order = 10,
					width = "double"
				},
				sunderchannel = {
					type = "select",
					name = L["Channel"],
					values = {AUTO = L["Instance"], SAY = L["Say"], YELL = L["Yell"], SELF = L["Self"]},
					order = 20,
					width = "double"
				},
				sunderbossonly = {
					type = "toggle",
					name = L["Only for bosses."],
					desc = L["Enable this only against bosses."],
					order = 30,
					width = "double"
				},
				empty_2 = {
					type = "description",
					name = " ",
					width = "full",
					order = 31
				},
				sunderdelay = {
					type = "range",
					name = L["Refresh"],
					desc = L["Number of seconds after application to count refreshs."],
					min = 0,
					max = 30,
					step = 1,
					order = 40,
					width = "double"
				}
			}
		}
	end

	---------------------------------------------------------------------------

	get_actor_sunder_sources = function(self, name, tbl)
		if not self.sunder or not name then return end

		tbl = clear(tbl or C)

		local total = 0
		local actors = self.actors
		for actorname, actor in pairs(actors) do
			local count = actor.sundertargets and actor.sundertargets[name]
			if count then
				local t = new()
				t.id = actor.id
				t.class = actor.class
				t.role = actor.role
				t.spec = actor.spec
				t.enemy = actor.enemy
				t.count = count
				tbl[actorname] = t
				-- add to total
				total = total + count
			end
		end
		return tbl, total
	end

	get_actor_sunder_targets = function(self, name, id, tbl)
		local actor = self:GetActor(name, id)
		local total = actor and actor.sunder
		if not actor or not actor.sundertargets then return end

		tbl = clear(tbl or C)
		for targetname, count in pairs(actor.sundertargets) do
			tbl[targetname] = new()
			tbl[targetname].count = count
			self:_fill_actor_table(tbl[targetname], targetname)
		end
		return tbl, total, actor
	end
end)
