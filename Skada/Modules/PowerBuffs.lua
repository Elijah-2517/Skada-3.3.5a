local _, Skada = ...
local Private = Skada.Private
Skada:RegisterModule("Power Buffs", function(L)
	local mode = Skada:NewModule("Power Buffs")
	local mode_spell = mode:NewModule("Spell List")

	local pairs, format, uformat = pairs, string.format, Private.uformat
	local GetSpellInfo, UnitGUID, UnitName, UnitBuff = GetSpellInfo, UnitGUID, UnitName, UnitBuff
	local classfmt = Skada.classcolors.format
	local mode_cols = nil

	-- buffs received from another player or an engineering trinket.
	local power_buffs = {
		[10060] = true, -- Power Infusion
		[23060] = true, -- Battle Squawk
		[49016] = true, -- Hysteria
		[57933] = true -- Tricks of the Trade
	}
	local last = {} -- [dstGUID:spellid] = timestamp, drops duplicate deliveries

	local function format_valuetext(d, total, metadata, subview)
		d.valuetext = Skada:FormatValueCols(
			mode_cols.Count and d.value,
			mode_cols[subview and "sPercent" or "Percent"] and Skada:FormatPercent(d.value, total)
		)

		if metadata and d.value > metadata.maxvalue then
			metadata.maxvalue = d.value
		end
	end

	local function log_buff(set, actorname, actorid, actorflags, spellid)
		local actor = Skada:GetActor(set, actorname, actorid, actorflags)
		if not actor then return end

		actor.powerbuff = (actor.powerbuff or 0) + 1
		set.powerbuff = (set.powerbuff or 0) + 1
		actor.powerbuffspells = actor.powerbuffspells or {}
		actor.powerbuffspells[spellid] = (actor.powerbuffspells[spellid] or 0) + 1
	end

	local function buff_applied(t)
		if not t.spellid or not power_buffs[t.spellid] or not t.dstGUID then return end

		local key = t.dstGUID .. ":" .. t.spellid
		if t.timestamp and last[key] == t.timestamp then return end
		last[key] = t.timestamp

		Skada:DispatchSets(log_buff, t.dstName, t.dstGUID, t.dstFlags, t.spellid)
	end

	-- buffs cast right before the pull are already up when combat starts.
	function mode:CombatEnter()
		for unit in Skada.UnitIterator(true) do
			local guid = UnitGUID(unit)
			if guid then
				local name = Private.UnitFullname and Private.UnitFullname(unit) or UnitName(unit)
				for i = 1, 40 do
					local aura, _, _, _, _, _, _, _, _, _, spellid = UnitBuff(unit, i)
					if not aura then break end
					if power_buffs[spellid] then
						Skada:DispatchSets(log_buff, name, guid, Private.DEFAULT_FLAGS, spellid)
					end
				end
			end
		end
	end

	function mode:CombatLeave()
		Private.clearTable(last)
	end

	function mode_spell:Enter(win, id, label, class)
		win.actorid, win.actorname, win.actorclass = id, label, class
		win.title = format(L["%s's power buffs"], classfmt(class, label))
	end

	function mode_spell:Update(win, set)
		win.title = uformat(L["%s's power buffs"], classfmt(win.actorclass, win.actorname))
		if not set or not win.actorname then return end

		local actor = Skada:FindActor(set, win.actorname, win.actorid, true)
		local total = actor and actor.powerbuff
		local spells = (total and total > 0) and actor.powerbuffspells

		if not spells then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for spellid, count in pairs(spells) do
			local name, _, icon = GetSpellInfo(spellid)
			nr = nr + 1

			local d = win:nr(nr)
			d.id = spellid
			d.spellid = spellid
			d.label = name or L["Unknown"]
			d.icon = icon
			d.value = count
			format_valuetext(d, total, win.metadata, true)
		end
	end

	function mode:Update(win, set)
		win.title = win.class and format("%s (%s)", L["Power Buffs"], L[win.class]) or L["Power Buffs"]

		local total = set and set:GetTotal(win.class, nil, "powerbuff")
		if not total or total == 0 then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for actorname, actor in pairs(set.actors) do
			if win:show_actor(actor, set, true) and actor.powerbuff then
				nr = nr + 1

				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = actor.powerbuff
				format_valuetext(d, total, win.metadata)
			end
		end
	end

	function mode:GetSetSummary(set, win)
		if not set then return end
		return set:GetTotal(win and win.class, nil, "powerbuff") or 0
	end

	function mode:OnEnable()
		mode_spell.metadata = {}
		self.metadata = {
			showspots = true,
			ordersort = true,
			filterclass = true,
			click1 = mode_spell,
			columns = {Count = true, Percent = false, sPercent = false},
			icon = [[Interface\ICONS\spell_holy_powerinfusion]]
		}

		mode_cols = self.metadata.columns

		Skada:RegisterForCL(buff_applied, {dst_is_interesting_nopets = true}, "SPELL_AURA_APPLIED", "SPELL_AURA_REFRESH")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_ENTER", "CombatEnter")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_LEAVE", "CombatLeave")
		Skada:AddMode(self, "Buffs and Debuffs")
	end

	function mode:OnDisable()
		Skada:UnregisterFromCL(buff_applied)
		Skada.UnregisterAllMessages(self)
		Skada:RemoveMode(self)
	end
end)
