# Coordination report

**Document:** TORRE-DEMO.nwf  
**Profile:** default (8df36eb5ded1)  
**Raw clashes:** 54, **issues:** 35, **decisions:** 9

CRITICAL 1 · HIGH 26 · MEDIUM 8 · LOW 0

## Evidence scope

- 1 test(s) never run: no results does NOT mean clean
- no results for required pairs: ARC-HVAC, FIRE-HVAC (clean or untested; verify)
- the filter rejected every result of: ARC vs STR

## Root causes

- **The same crossing (Ducts/Rectangular Duct x Structural Framing/Concrete-Rectangular Beam) repeats on 5 levels** (90%). Fix the typical detail (Ducts/Rectangular Duct x Structural Framing/Concrete-Rectangular Beam) once and replicate it on 5 levels.
- **Riser duct R1 is the movable party in 5 issues** (70%). Resolving Riser duct R1 in one decision closes 5 issues.
- **The same crossing (Ducts/Rectangular Duct x Floors/Floor:Concrete 200) repeats on 5 levels** (90%). Fix the typical detail (Ducts/Rectangular Duct x Floors/Floor:Concrete 200) once and replicate it on 5 levels.
- **The same crossing (Cable Trays/Cable Tray:200x60 x Pipes/Pipe Types:Copper 50) repeats on 5 levels** (90%). Fix the typical detail (Cable Trays/Cable Tray:200x60 x Pipes/Pipe Types:Copper 50) once and replicate it on 5 levels.
- **The same crossing (Conduits/Conduit:EMT 25 x Walls/Basic Wall) repeats on 5 levels** (90%). Fix the typical detail (Conduits/Conduit:EMT 25 x Walls/Basic Wall) once and replicate it on 5 levels.

## Top issues

### NW-9504F9 · CRITICAL · 72.7
HVAC x Structure, L3, 1 clashes
- penetrates 300 mm, 100% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-13CE10 · HIGH · 60.9
HVAC x Structure, L5, 1 clashes
- penetrates 173 mm, 58% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-1402F6 · HIGH · 59.5
HVAC x Structure, L4, 1 clashes
- penetrates 157 mm, 52% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-FBBC8F · HIGH · 57.4
HVAC x Structure, L1, 1 clashes
- penetrates 135 mm, 45% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-041769 · HIGH · 57.1
HVAC x Structure, L5, 1 clashes
- penetrates 132 mm, 44% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-7DB8E7 · HIGH · 56.5
HVAC x Structure, L5, 1 clashes
- penetrates 125 mm, 42% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-709927 · HIGH · 56.0
HVAC x Structure, L2, 1 clashes
- penetrates 120 mm, 40% of the element's smallest dimension
- HVAC against Structure is a 90% criticality crossing
- Structure can hardly move; HVAC has to adjust
- **Action:** HVAC must reroute or shift; Structure stays.

### NW-B3C2A8 · HIGH · 55.7
Fire protection x Structure, L2, 1 clashes
- penetrates 30 mm, 43% of the element's smallest dimension
- Fire protection against Structure is a 85% criticality crossing
- Structure can hardly move; Fire protection has to adjust
- **Action:** Fire protection must reroute or shift; Structure stays.

