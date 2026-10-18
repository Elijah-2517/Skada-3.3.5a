-- Skada-WotLK-Netic: TWW (5Buttons) label positioning.
-- Theme presets are registered in Core/Display/Bar.lua.
-- Default window settings stay unchanged; themes are selected manually.
local _, Skada = ...
if not Skada then return end
local pairs, hooksecurefunc = pairs, hooksecurefunc

local TWW_BAR_TEXTURE = "TWW Bar"
local TWW_TEXT_Y_OFFSET = 6

local SLB = LibStub("SpecializedLibBars-1.0", true)
if not SLB then return end

-- extend SpecializedLibBars so bar groups can carry a per-window label offset.
if not SLB.barListPrototype.SetBarTextYOffset then
	local orig = SLB.barPrototype.UpdateOrientationLayout
	local LEFT_TO_RIGHT = 1

	SLB.barPrototype.UpdateOrientationLayout = function(self, orientation)
		orig(self, orientation)
		local offset = self.ownerGroup and self.ownerGroup._textYOffset or 0
		if offset == 0 then return end
		if orientation == LEFT_TO_RIGHT then
			self.timerLabel:SetPoint("RIGHT", self, "RIGHT", -5, offset)
			self.label:SetPoint("LEFT", self, "LEFT", 5, offset)
		else
			self.timerLabel:SetPoint("LEFT", self, "LEFT", 5, offset)
			self.label:SetPoint("RIGHT", self, "RIGHT", -5, offset)
		end
	end

	SLB.barListPrototype.SetBarTextYOffset = function(self, offset)
		offset = offset or 0
		if self._textYOffset == offset then return end
		self._textYOffset = offset
		for _, bar in pairs(self:GetBars()) do
			bar:UpdateOrientationLayout(self.orientation or LEFT_TO_RIGHT)
		end
	end

	local origNewBar = SLB.barListPrototype.NewBar
	SLB.barListPrototype.NewBar = function(self, name, text, value, maxVal, icon)
		local bar, isNew = origNewBar(self, name, text, value, maxVal, icon)
		if self._textYOffset and self._textYOffset ~= 0 then
			bar:UpdateOrientationLayout(self.orientation or LEFT_TO_RIGHT)
		end
		return bar, isNew
	end
end

local function SyncTextOffsets()
	local windows = Skada.windows
	for i = 1, #windows do
		local win = windows[i]
		local bargroup = win and win.bargroup
		if bargroup and bargroup.SetBarTextYOffset then
			local offset = (win.db and win.db.bartexture == TWW_BAR_TEXTURE) and TWW_TEXT_Y_OFFSET or 0
			bargroup:SetBarTextYOffset(offset)
		end
	end
end

hooksecurefunc(Skada, "ApplySettings", SyncTextOffsets)
