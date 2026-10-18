"""Compare effective Skada settings using its bundled AceDB (requires lupa).

Usage: python skada_settings_compat.py OLD_ADDON CANDIDATE_ADDON
Optional: --saved-vars PATH (repeatable; files are read only).
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

from lupa.lua51 import LuaRuntime, lua_type


SETUP = r'''
strmatch = string.match
function wipe(t) for k in pairs(t) do t[k] = nil end return t end
function clone(src)
 local dest = {}
 for k,v in pairs(src) do dest[k] = type(v)=='table' and clone(v) or v end
 return dest
end
function CreateFrame()
 return {SetScript=function() end, RegisterEvent=function() end}
end
function GetRealmName() return 'CompatibilityRealm' end
function UnitName() return 'CompatibilityCharacter' end
function UnitClass() return 'Hunter','HUNTER' end
function UnitRace() return 'Human','Human' end
function UnitFactionGroup() return 'Alliance' end
hooks={}
function hooksecurefunc(_,_,fn) hooks[#hooks+1]=fn end
Skada={windows={}, Private={tCopy=function(dest,src)
 for k,v in pairs(clone(src)) do dest[k]=v end
end}}
'''


def plain(value):
    if lua_type(value) == "table":
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, bool):
        return ("boolean", value)  # Python otherwise considers False equal to Lua 0.
    return value


def runtime(addon):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(SETUP)
    for file in ("Libs/LibStub/LibStub.lua", "Libs/AceDB-3.0/AceDB-3.0.lua"):
        lua.execute((addon / file).read_text(encoding="utf-8-sig"))
    lua.execute('''
    local slb=LibStub:NewLibrary('SpecializedLibBars-1.0',1)
    slb.barListPrototype={NewBar=function() return {},true end}
    slb.barPrototype={UpdateOrientationLayout=function() end}
    ''')
    options = (addon / "Core/Options.lua").read_text(encoding="utf-8-sig")
    start = options.index("Skada.windowdefaults = {")
    end = options.index("\n-------------------------------------------------------------------------------", start)
    lua.execute('local folder,Private="Skada",Skada.Private\n' + options[start:end])
    # Follow the load manifest: an unused file must not affect the result.
    manifest = ET.parse(addon / "Modules/Load.xml").getroot()
    for item in manifest:
        filename = item.attrib.get("file", "")
        if filename.startswith("Theme") and filename.endswith(".lua"):
            lua.execute((addon / "Modules" / filename).read_text(encoding="utf-8-sig"),
                        "Skada", lua.globals().Skada)
    return lua


def effective_settings(addon, saved_source=None):
    lua = runtime(addon)
    if saved_source is None:
        lua.execute('''
        SkadaDB={profiles={
         Sparse={windows={{name='Main',barwidth=333}}},
         Custom={mergepets=false,firsthit=false,
          modulesBlocked={['Player vs. Player']=false},
          windows={{name='Custom',barheight=22,enabletitle=false,snapto=false,
           buttons={menu=false},title={height=27,textcolor={r=.2,g=.4,b=.6,a=.8}},
           background={color={r=.1,g=.2,b=.3,a=.7}}},
           {name='Second',barheight=19,barwidth=250,title={height=21}}}},
         Empty={}
        },global={customSetting=false}}
        ''')
    else:
        lua.execute(saved_source)
        if lua_type(lua.globals().SkadaDB) != "table":
            return None
    lua.execute('''
    db=LibStub('AceDB-3.0'):New(clone(SkadaDB),Skada.defaults,true)
    profileNames={}
    for name in pairs(db.sv.profiles or {}) do profileNames[#profileNames+1]=name end
    table.sort(profileNames)
    function snapshotProfiles()
     local result={}
     for _,name in ipairs(profileNames) do
      db:SetProfile(name)
      Skada.profile=db.profile
      Skada.windows={}
      for _,settings in ipairs(db.profile.windows or {}) do
       Skada.windows[#Skada.windows+1]={db=settings,bargroup={
        SetBarTextYOffset=function(self,offset) self.offset=offset end}}
      end
      for _,hook in ipairs(hooks) do hook() end
      for _,win in ipairs(Skada.windows) do
       local expected=win.db.bartexture=='TWW Bar' and 6 or 0
       assert(win.bargroup.offset==nil or win.bargroup.offset==expected)
      end
      result[name]=clone(db.profile)
     end
     return result
    end
    first=snapshotProfiles()
    db:RegisterDefaults(nil)
    stripped=clone(db.sv)
    db=LibStub('AceDB-3.0'):New(stripped,Skada.defaults,true)
    second=snapshotProfiles()
    ''')
    first = plain(lua.globals().first)
    if first != plain(lua.globals().second):
        raise AssertionError("Effective settings changed after AceDB save/reload")
    return first, plain(lua.globals().Skada.windowdefaults)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_addon", type=Path)
    parser.add_argument("candidate_addon", type=Path)
    parser.add_argument("--saved-vars", type=Path, action="append", default=[])
    args = parser.parse_args()
    sources = [None] + [path.read_text(encoding="utf-8-sig") for path in args.saved_vars]
    checked = profiles = 0
    for source in sources:
        old = effective_settings(args.old_addon, source)
        candidate = effective_settings(args.candidate_addon, source)
        if old != candidate:
            # Do not expose character names or saved profile contents in output.
            raise AssertionError("Candidate changed effective profile/window defaults")
        if old is not None:
            checked += 1
            profiles += len(old[0])
    print(f"PASS: {checked} databases, {profiles} profiles; effective settings and AceDB round trips match")


if __name__ == "__main__":
    main()
