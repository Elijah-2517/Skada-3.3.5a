local _, Skada = ...
local Private = Skada.Private
Skada:RegisterModule("Potions", function(L, P, G, C, _, O)
	local mode = Skada:NewModule("Potions")
	local mode_spell = mode:NewModule("Spell List")
	local mode_actor = mode_spell:NewModule("Target List")
	local get_actors_by_potion = nil
	local mode_cols = nil

	local pairs, format, strsub, uformat = pairs, string.format, string.sub, Private.uformat
	local GetItemInfo, classcolors, classfmt = GetItemInfo, Skada.classcolors, Skada.classcolors.format
	local new, del, clear = Private.newTable, Private.delTable, Private.clearTable
	local prepotionStr, potionStr = "\124c%s%s\124r %s", "\124T%s:14:14:0:0:64:64:4:60:4:60\124t"
	local potion_ids, prepotion = {}, {}

	local function format_valuetext(d, total, metadata, subview)
		d.valuetext = Skada:FormatValueCols(
			mode_cols.Count and d.value,
			mode_cols[subview and "sPercent" or "Percent"] and Skada:FormatPercent(d.value, total)
		)

		if metadata and d.value > metadata.maxvalue then
			metadata.maxvalue = d.value
		end
	end

	local long_ids = {
		[53758]="46379", [53755]="46376", [54212]="46378", [53760]="46377",
		[53746]="40068", [53748]="40073", [53749]="40076", [53747]="40072", [33721]="40070",
		[53751]="40078", [53752]="40079", [53763]="40097", [53764]="40109",
		[28497]="39666", [60340]="44325", [60341]="44327", [60343]="44328",
		[60344]="44329", [60345]="44330", [60346]="44331", [60347]="44332",
	}

	local food_ids = { [57356]=true, [57358]=true, [57360]=true, [57367]=true, [57365]=true, [57371]=true, [57399]=true, [57329]=true, [57332]=true, [57327]=true, [57325]=true, [57334]=true }

	local function state()
		Skada.sets.consumables = Skada.sets.consumables or {pending={}, known={}, ledger={actors={}, consumableledger=true}}
		return Skada.sets.consumables
	end

	local function log_potion(set, name, id, flags, item, count, inferred)
		local actor
		if set.consumableledger then
			actor = set.actors[name] or {id=id,flag=flags}
			set.actors[name] = actor
		else actor = Skada:GetActor(set, name, id, flags) end
		if not actor then return end
		count = count or 1
		actor.potion = (actor.potion or 0) + count
		set.potion = (set.potion or 0) + count
		actor.potionspells = actor.potionspells or {}
		actor.potionspells[item] = (actor.potionspells[item] or 0) + count
		if inferred then
			actor.potioninferred = actor.potioninferred or {}
			actor.potioninferred[item] = true
		end
	end

	local function log_current(set, ...)
		if set ~= Skada.total and not set.stopped then log_potion(set, ...) end
	end

	local function record(name, id, flags, item, long, inferred)
		if not Skada.sets then return end
		local data = state()
		local total = Skada:EnsureTotalSet()
		-- Keep a complete total, including consumables used outside saved fights.
		if not data.initialized then
			for actorname, actor in pairs(total.actors) do
				local classified = 0
				for potion, count in pairs(actor.potionspells or {}) do
					classified = classified + count
					log_potion(data.ledger, actorname, actor.id, actor.flag, potion, count)
				end
				if (actor.potion or 0) > classified then log_potion(data.ledger,actorname,actor.id,actor.flag,"s0",actor.potion-classified) end
			end
			data.initialized = true
		end
		log_potion(total, name, id, flags, item, 1, inferred)
		log_potion(data.ledger, name, id, flags, item, 1, inferred)
		if not long then
			if Skada.inCombat and Skada.current then
				Skada:DispatchSets(log_current, name, id, flags, item)
			else
				local key = id .. ":" .. item
				local entry = data.pending[key]
				if entry then entry.count = entry.count + 1
				else data.pending[key] = {name=name,id=id,flags=flags,item=item,count=1} end
			end
		end
		Skada.changed = true
	end

	function mode:CombatEvent(_, t)
		if food_ids[t.spellid] and t.event == "SPELL_AURA_APPLIED" then
			if t:DestInGroup(true) then
				local data = state()
				data.last = data.last or {}
				local key = t.dstGUID .. ":food:" .. t.spellid
				if t.timestamp and data.last[key] == t.timestamp then return end
				data.last[key] = t.timestamp
				record(t.dstName,t.dstGUID,t.dstFlags,"s"..t.spellid,true)
			end
			return
		end
		if t.event ~= "SPELL_CAST_SUCCESS" or not t:SourceInGroup(true) then return end
		local item = potion_ids[t.spellid] or long_ids[t.spellid]
		if not item then return end
		local data = state()
		-- A duplicate delivery of the same cast must not add another use.
		local key = t.srcGUID .. ":" .. t.spellid
		data.last = data.last or {}
		if t.timestamp and data.last[key] == t.timestamp then return end
		data.last[key] = t.timestamp
		if long_ids[t.spellid] then data.known[key] = true end
		record(t.srcName, t.srcGUID, t.srcFlags, item, long_ids[t.spellid])
	end

	function mode:CombatEnter()
		local data = state()
		for _, entry in pairs(data.pending) do
			Skada:DispatchSets(log_current, entry.name, entry.id, entry.flags, entry.item, entry.count)
		end
		if P.prepotion then
			clear(prepotion)
			for _,entry in pairs(data.pending) do
				local name = GetItemInfo(entry.item) or entry.item
				prepotion[#prepotion+1] = format("%s: %s x%d",entry.name,name,entry.count)
			end
		end
		wipe(data.pending)
		-- One scan per pull, including auras whose caster is unavailable.
		for unit in Skada.UnitIterator(true) do
			local id = UnitGUID(unit)
			local name = Private.UnitFullname and Private.UnitFullname(unit) or UnitName(unit)
			for i=1,40 do
				local aura, _, _, _, _, _, _, _, _, _, spell = UnitBuff(unit,i)
				if not aura then break end
				local item = long_ids[spell]
				local key = id and (id .. ":" .. spell)
				if item and key and not data.known[key] then
					data.known[key] = true
					record(name,id,Private.DEFAULT_FLAGS,item,true,true)
				end
			end
		end
	end

	function mode:CombatLeave()
		if P.prepotion and #prepotion > 0 then Skada:Printf(L["pre-potion: %s"],table.concat(prepotion,", ")) end
		clear(prepotion)
	end

	function mode:DataReset()
		Skada.sets.consumables = nil
		clear(prepotion)
	end

	function mode:RestoreTotal()
		local data = Skada.sets.consumables
		if not data or not data.initialized then return end
		local total = Skada.total
		total.potion = nil
		for _,actor in pairs(total.actors) do actor.potion=nil; actor.potionspells=nil; actor.potioninferred=nil end
		for name,actor in pairs(data.ledger.actors) do
			for item,count in pairs(actor.potionspells or {}) do
				log_potion(total,name,actor.id,actor.flag,item,count,actor.potioninferred and actor.potioninferred[item])
			end
		end
	end

	function mode_actor:Enter(win, id, label)
		win.spellid, win.spellname = id, label
		win.title = label
	end

	function mode_actor:Update(win, set)
		win.title = win.spellname or L["Unknown"]
		if win.class then
			win.title = format("%s (%s)", win.title, L[win.class])
		end

		if not set or not win.spellname then return end

		local total, actors = get_actors_by_potion(set, win.spellid, win.class)
		if total == 0 or not actors then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for actorname, actor in pairs(actors) do
			nr = nr + 1

			local d = win:actor(nr, actor, actor.enemy, actorname)
			d.value = actor.count
			format_valuetext(d, total, win.metadata, true)
		end
	end

	function mode_spell:Enter(win, id, label, class)
		win.actorid, win.actorname, win.actorclass = id, label, class
		win.title = format(L["%s's potions"], classfmt(class, label))
	end

	local function request_potion(potionid)
		if potionid and potionid ~= nil and potionid ~= "" and potionid ~= 0 and strsub(potionid, 1, 1) ~= "s" then
			GameTooltip:SetHyperlink(format("item:%s:0:0:0:0:0:0:0", potionid))
			GameTooltip:Hide()
		end
	end

	function mode_spell:Update(win, set)
		win.title = uformat(L["%s's potions"], classfmt(win.actorclass, win.actorname))
		if not set or not win.actorname then return end

		local actor = Skada:FindActor(set, win.actorname, win.actorid, true)
		local total = actor and actor.potion
		local potions = (total and total > 0) and actor.potionspells

		if not potions then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		for potionid, count in pairs(potions) do
			local potionname, potionlink, potionicon
			if strsub(potionid,1,1) == "s" then
				local id = tonumber(strsub(potionid,2))
				local rank
				potionname, rank, potionicon = GetSpellInfo(id)
				potionlink = GetSpellLink(id)
				if id == 0 then potionname=L["Unknown"] end
			else
				local a,b,c,d,e,f,g
				potionname, potionlink, a,b,c,d,e,f,g,potionicon = GetItemInfo(potionid)
			end
			if not potionname then
				request_potion(potionid)
			end

			if potionname then
				nr = nr + 1
				local d = win:nr(nr)

				d.id = potionid
				d.hyperlink = potionlink
				d.label = potionname .. ((actor.potioninferred and actor.potioninferred[potionid]) and (" (" .. L["Detected on player"] .. ")") or "")
				d.icon = potionicon

				d.value = count
				format_valuetext(d, total, win.metadata, true)
			end
		end
	end

	function mode:Update(win, set)
		win.title = win.class and format("%s (%s)", L["Potions"], L[win.class]) or L["Potions"]

		local total = set and set:GetTotal(win.class, nil, "potion")
		if not total or total == 0 then
			return
		elseif win.metadata then
			win.metadata.maxvalue = 0
		end

		local nr = 0
		local actors = set.actors

		for actorname, actor in pairs(actors) do
			if win:show_actor(actor, set, true) and actor.potion then
				nr = nr + 1

				local d = win:actor(nr, actor, actor.enemy, actorname)
				d.value = actor.potion
				format_valuetext(d, total, win.metadata)
			end
		end
	end

	function mode:GetSetSummary(set, win)
		if not set then return end
		return set:GetTotal(win and win.class, nil, "potion") or 0
	end

	function mode:OnEnable()
		mode_actor.metadata = {filterclass = true}
		mode_spell.metadata = {click1 = mode_actor}
		self.metadata = {
			showspots = true,
			ordersort = true,
			filterclass = true,
			click1 = mode_spell,
			columns = {Count = true, Percent = false, sPercent = false},
			icon = [[Interface\ICONS\inv_potion_31]]
		}

		mode_cols = self.metadata.columns

		-- no total click.
		mode_spell.nototal = true

		Skada.RegisterCallback(self, "Skada_ConsumableEvent", "CombatEvent")
		Skada.RegisterCallback(self, "Skada_DataReset", "DataReset")
		Skada.RegisterCallback(self, "Skada_TotalRebuilt", "RestoreTotal")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_ENTER", "CombatEnter")
		Skada.RegisterMessage(self, "COMBAT_PLAYER_LEAVE", "CombatLeave")
		Skada.RegisterCallback(self, "Skada_ApplySettings", "ApplySettings")
		Skada:AddMode(self)
	end

	function mode:OnDisable()
		Skada.UnregisterAllCallbacks(self)
		Skada.UnregisterAllMessages(self)
		Skada:RemoveMode(self)
	end

	function mode:ApplySettings() end

	function mode:OnInitialize()
		potion_ids[28714] = "22788" -- Flame Cap
		-- list of potion: [spellid] = potionid (string)

		--[[ level NaN ]]--
		potion_ids[439] = "118" -- Minor Healing Potion
		potion_ids[6724] = "5816" -- Light of Elune
		potion_ids[29236] = "3087" -- Mug of Shimmer Stout
		potion_ids[47430] = "36770" -- Zort's Protective Elixir
		potion_ids[50809] = "38351" -- Murliver Oil

		--[[ level 03-17 ]]--
		potion_ids[437] = "2455" -- Minor Mana Potion
		potion_ids[438] = "3385" -- Lesser Mana Potion
		potion_ids[440] = "4596" -- Discolored Healing Potion
		potion_ids[441] = "929" -- Healing Potion
		potion_ids[2370] = "2456" -- Minor Rejuvenation Potion
		potion_ids[2379] = "2459" -- Swiftness Potion
		potion_ids[2380] = "3384" -- Minor Magic Resistance Potion
		potion_ids[6612] = "5631" -- Rage Potion
		potion_ids[6612] = "858" -- Lesser Healing Potion
		potion_ids[6614] = "5632" -- Cowardly Flight Potion
		potion_ids[7242] = "6048" -- Shadow Protection Potion
		potion_ids[7245] = "6051" -- Holy Protection Potion
		potion_ids[7840] = "6372" -- Swim Speed Potion
		potion_ids[26677] = "3386" -- Potion of Curing

		--[[ level 20-28 ]]--
		potion_ids[2023] = "3827" -- Mana Potion
		potion_ids[2024] = "1710" -- Greater Healing Potion
		potion_ids[3592] = "2633" -- Jungle Remedy
		potion_ids[3680] = "3823" -- Lesser Invisibility Potion
		potion_ids[6613] = "5633" -- Great Rage Potion
		potion_ids[6615] = "5634" -- Free Action Potion
		potion_ids[7233] = "6049" -- Fire Protection Potion
		potion_ids[7239] = "6050" -- Frost Protection Potion
		potion_ids[7254] = "6052" -- Nature Protection Potion

		--[[ level 31-37 ]]--
		potion_ids[4042] = "3928" -- Superior Healing Potion
		potion_ids[4941] = "4623" -- Lesser Stoneshield Potion
		potion_ids[11359] = "9030" -- Restorative Potion
		potion_ids[11364] = "9036" -- Magic Resistance Potion
		potion_ids[11387] = "9144" -- Wildvine Potion
		potion_ids[11392] = "9172" -- Invisibility Potion
		potion_ids[11903] = "6149" -- Greater Mana Potion
		potion_ids[15822] = "12190" -- Dreamless Sleep Potion
		potion_ids[21394] = "17349" -- Superior Healing Draught
		potion_ids[21396] = "17352" -- Superior Mana Draught

		--[[ level 41-49 ]]--
		potion_ids[3169] = "3387" -- Limited Invulnerability Potion
		potion_ids[17528] = "13442" -- Mighty Rage Potion
		potion_ids[17530] = "13443" -- Superior Mana Potion
		potion_ids[17540] = "13455" -- Greater Stoneshield Potion
		potion_ids[17543] = "13457" -- Greater Fire Protection Potion
		potion_ids[17544] = "13456" -- Greater Frost Protection Potion
		potion_ids[17545] = "13460" -- Greater Holy Protection Potion
		potion_ids[17546] = "13458" -- Greater Nature Protection Potion
		potion_ids[17548] = "13459" -- Greater Shadow Protection Potion
		potion_ids[17549] = "13461" -- Greater Arcane Protection Potion
		potion_ids[17550] = "13462" -- Purification Potion
		potion_ids[21393] = "17348" -- Major Healing Draught
		potion_ids[21395] = "17351" -- Major Mana Draught
		potion_ids[24364] = "20008" -- Living Action Potion

		--[[ level 50-55 ]]--
		potion_ids[17624] = "13506" -- Flask of Petrification
		potion_ids[22729] = "18253" -- Major Rejuvenation Potion
		potion_ids[24360] = "20002" -- Greater Dreamless Sleep Potion
		potion_ids[28492] = "22826" -- Sneaking Potion
		potion_ids[28548] = "22871" -- Shrouding Potion
		potion_ids[41617] = "32903" -- Cenarion Mana Salve
		potion_ids[41618] = "32902" -- Bottled Nethergon Energy
		potion_ids[41619] = "32904" -- Cenarion Healing Salve
		potion_ids[41620] = "32905" -- Bottled Nethergon Vapor
		potion_ids[52697] = "39327" -- Noth's Special Brew
		potion_ids[67486] = "33092" -- Healing Potion Injector
		potion_ids[67487] = "33093" -- Mana Potion Injector

		--[[ level 60-65 ]]--
		potion_ids[17531] = "31840" -- Major Combat Mana Potion
		potion_ids[17534] = "31838" -- Major Combat Healing Potion
		potion_ids[28504] = "22836" -- Major Dreamless Sleep Potion
		potion_ids[28506] = "22837" -- Heroic Potion
		potion_ids[28507] = "22838" -- Haste Potion
		potion_ids[28508] = "22839" -- Destruction Potion
		potion_ids[28511] = "22841" -- Major Fire Protection Potion
		potion_ids[28512] = "22842" -- Major Frost Protection Potion
		potion_ids[28513] = "22844" -- Major Nature Protection Potion
		potion_ids[28515] = "22849" -- Ironshield Potion
		potion_ids[28517] = "22850" -- Super Rejuvenation Potion
		potion_ids[28536] = "22845" -- Major Arcane Protection Potion
		potion_ids[28537] = "22846" -- Major Shadow Protection Potion
		potion_ids[28538] = "22847" -- Major Holy Protection Potion
		potion_ids[38908] = "31676" -- Fel Regeneration Potion
		potion_ids[45051] = "34440" -- Mad Alchemist's Potion

		--[[ level 70 ]]--
		potion_ids[28494] = "22828" -- Insane Strength Potion
		potion_ids[28495] = "43569" -- Endless Healing Potion
		potion_ids[28499] = "43570" -- Endless Mana Potion
		potion_ids[38929] = "31677" -- Fel mana potion
		potion_ids[41304] = "32783" -- Blue Ogre Brew
		potion_ids[41306] = "32784" -- Red Ogre Brew
		potion_ids[43185] = "33447" -- Healing Potion
		potion_ids[43186] = "33448" -- Restore Mana
		potion_ids[53750] = "40077" -- Crazy Alchemist's Potion
		potion_ids[53753] = "40081" -- Nightmare Slumber
		potion_ids[53761] = "40087" -- Powerful Rejuvenation Potion
		potion_ids[53762] = "40093" -- Indestructible
		potion_ids[53908] = "40211" -- Potion of Speed
		potion_ids[53909] = "40212" -- Potion of Wild Magic
		potion_ids[53910] = "40213" -- Arcane Protection
		potion_ids[53911] = "40214" -- Fire Protection
		potion_ids[53913] = "40215" -- Frost Protection
		potion_ids[53914] = "40216" -- Nature Protection
		potion_ids[53915] = "40217" -- Shadow Protection
		potion_ids[61371] = "44728" -- Endless Rejuvenation Potion
		potion_ids[67489] = "41166" -- Runic Healing Injector
		potion_ids[67490] = "42545" -- Runic Mana Injector

		-- don't edit below unless you know what you're doing.
		if P.prepotion == nil then
			P.prepotion = true
		end

		O.tweaks.args.general.args.prepotion = {
			type = "toggle",
			name = L["Pre-potion"],
			desc = L["Prints pre-potion after the end of the combat."],
			order = 0
		}
	end

	---------------------------------------------------------------------------

	get_actors_by_potion = function(self, potionid, class, tbl)
		local total = 0
		if not self.actors or not self.potion or not potionid then
			return total
		end

		tbl = clear(tbl or C)

		local actors = self.actors
		for aname, a in pairs(actors) do
			if a.potionspells and a.potionspells[potionid] and (not class or class == a.class) then
				total = total + a.potionspells[potionid]
				tbl[aname] = new()
				tbl[aname].id = a.id
				tbl[aname].class = a.class
				tbl[aname].role = a.role
				tbl[aname].spec = a.spec
				tbl[aname].enemy = a.enemy
				tbl[aname].count = a.potionspells[potionid]
			end
		end

		return total, tbl
	end
end)
