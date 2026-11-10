# Skylark

A browser flight simulator: fly an F-15C, an F/A-18C Hornet, an F-22A Raptor, a Sukhoi Su-57, a Eurofighter Typhoon, a Sukhoi Su-30SM, a Sukhoi Su-34, a Boeing 737 MAX 8, a Boeing 747-8, Concorde, a B-2 Spirit or an AH-64D Apache attack helicopter from a huge military airbase next to a destructible city.
Open `index.html` through any static web server. The F-15C, F/A-18C, F-22A, Su-57, Typhoon, Su-30SM, Su-34, 737 MAX 8, 747-8, Concorde, B-2 Spirit and AH-64D are adapted Sketchfab models (see MODEL_CREDITS.md); the other aircraft models (`*.gltf.json`) were built in Blender, and the Su-30SM stand-in rebuilds with `blender --background --python su30/build_su30.py -- SU30.gltf.json`.

## Multiplayer

Everyone who has the page open flies in the same world under a callsign picked on the first visit (click the player count to change it). There is no server: the pages connect to each other directly over WebRTC with [Trystero](https://github.com/dmotz/trystero), finding each other through public Nostr relays. Players whose networks block direct connections (mobile data, school or office Wi-Fi) go through a Metered TURN relay; its API key is in the page, so its usage limit is set in Metered. Players see each other's aircraft with name tags. Bomb, shell and crash blasts, cannon hits and nuclear blasts happen in everyone's copy of the city. A player who joins late catches up on the damage from someone already there.

- Cannon rounds, bombs and shells hit other players' aircraft. A hit tears off the part it lands on (shoot the right wing and the right wing comes off, cut at the point hit), as flying into a building does. Enough hits on the fuselage, or a close blast, bring the aircraft down, and everyone sees who shot whom.
- Damage is local and progressive. Wings, tail surfaces, podded engines and gear legs tear off where they are hit; the fuselage is four sections (cockpit, forward, centre, rear), each going from intact through damaged, severely damaged and structurally compromised to destroyed, and bigger airframes take more. A missile burst hurts what is near it: a fighter caught by a direct hit is lost, an airliner usually flies on damaged. Hits on the cockpit hurt the crew: with the crew or the controls gone the aircraft flies on, out of control, until it hits something (the kill still counts). A failing rear fuselage takes the tail with it; a failing centre or forward fuselage breaks the aircraft up.
- Crashes scale with the impact: a slow, shallow strike or a gear-up landing is a belly slide that wears the airframe (dragging engines and wingtips are ground off); harder impacts break it into its structural parts, more of them the harder it hit (fuselage sections, whole wings, engines as units, the tail, gear legs), and the hardest dig a crater sized by the aircraft and the impact. Every player sees the same breakup.
- Air-to-air missiles are a separate loadout on the F-15C (4 × AIM-120C, 4 × AIM-9X), Typhoon (4 × AIM-120C, 2 × IRIS-T), Su-30SM (6 × R-77, 4 × R-73) and Su-34 (6 × R-77, 2 × R-73). The radar (APG-63, CAPTOR, N011M BARS, Sh141) shows other players in a cone ahead; L locks and cycles (a lock takes 1 s to acquire), X fires. The heat-seeker is used inside 15 km, the radar missile beyond (out to 50 km). Missiles steer by proportional navigation with limited g, and their proximity burst tears parts off like any blast. Targets get LOCKED and MISSILE warnings.
- Rooms: the game opens on the lobby, and you fly once you have joined a room (Public, one from the list, or your own). Leave room on the pause screen ends the flight and returns to the lobby. If multiplayer cannot connect, the lobby offers flying offline. The Rooms button (start and pause screens) lists the rooms in use with their player counts, joins one, or creates a new one by name. A hidden room is left out of the list and is joined by name or invite link (Copy invite link). Each room has its own players and its own shared city; a lobby room carries the list.
- Only one player at a time can fly the B-2 Spirit. Its air start is at 50,000 ft, and it carries 80 Mk-82s, 16 Mk-84s, 2 GBU-57s or 16 B83s in its bays.
- The B-2 is Low Observable (passive, always on): other players' radar picks it up at 60% of the normal range and takes twice as long (2 s instead of 1 s) to lock it. It can still be seen and hit by missiles.
- The F-22A Raptor's STEALTH is a passive ability, always on. Other players' radar detects it at 45% of the normal range, takes 2.2 times as long to lock it, and gives radar-guided missiles fired at it (AIM-120, R-77) 75% of their usual odds. Eyes, heat-seekers (AIM-9, R-73, IRIS-T) and guns are not affected.
- The F-22A has 2D thrust vectoring: both nozzles swing up and down together, up to 20°, following the stick. Thrust through the deflected nozzles adds pitch control in proportion to the thrust, so the nose stays controllable at low speed and high angles of attack. The nozzles never move sideways, so roll and yaw stay aerodynamic. The nozzles drawn on the model, and the HUD's TVC readout, show the same angle the physics uses.
- The F/A-18C Hornet has less power than the F-15C and a lower top speed, but its leading-edge extensions keep it turning and pointing its nose at very high angles of attack (7.5 g; Shift for harder turns that bleed speed fast). Its main gear folds aft, the nose gear forward, the gear doors swing shut behind them, and the tailhook drops with the gear.
- The F/A-18C has two loadouts, each on its own pylon rails:
  - Air superiority: an AIM-9M on each wingtip, and six AIM-120Cs on the outer and inner wing pylons and the engine nacelles.
  - Ground attack: six AGM-65F Mavericks, one on each inner pylon and two side by side on each outer pylon, and nothing else.
  - V shows the view through a Maverick's own seeker (only with Mavericks aboard). L locks the ground point and X fires one. Each flies off its rail under its motor and steers onto the point, out to 14 km.
  - Other players see its missiles and Mavericks on the jet, minus the ones fired.
- With missiles selected, 2 again picks one missile type (AIM-120C, AIM-9M, …) or goes back to the jet picking by range, on every fighter.
- The Su-57's LOW OBSERVABLE is a passive ability, always on, and depends on aspect. Seen from ahead, other players' radar detects it at 62% of the normal range; from the side or behind, at 85%. A lock takes 1.7 times as long, and radar-guided missiles fired at it get 85% of their usual odds. Eyes, heat-seekers and guns are not affected.
- The Su-57 has 3D thrust vectoring. Each nozzle swivels up, down and sideways inside a 15° cone, following the stick and the rudder; the nozzles split in pitch with roll input. This adds pitch and yaw control (and a little roll) in proportion to thrust, so the nose can be swung even when slow. With Shift it flies far past the stall, but hard manoeuvres bleed speed fast. Other players see the nozzles move as the pilot's physics moves them.
- The Su-57's air-superiority loadout carries 4 × R-77 and 2 × R-77M in its two tandem main bays and 2 × R-73 in the side bays. With a lock, X fires the shortest-reach radar missile that covers the range, keeping the R-77Ms for long shots.
- The Su-57's ground-strike loadout carries 2 × Kh-29T on under-wing pylons (shown only with this loadout) and 2 × KAB-500Kr in the main bays. V opens the EO sight under the nose: the arrows or the mouse slew it, + and − zoom, and L locks it onto the ground point under the cross. That point is the only target either weapon takes; with no lock, neither is released. 2 picks the weapon and X releases it, from the sight or from the normal view, where a TGT box marks the point.
  - Kh-29T: a TV-guided rocket. It needs the point within 12 km and 40° of the nose; it drops clear of the pylon, boosts to about 550 m/s and steers onto the point. Fire and forget.
  - KAB-500Kr: a guided bomb with no motor. Its fins correct its fall onto the point within about half the load a GBU-32's can make. The sight says IN ZONE when a release can reach; out of zone, it falls short.
  - Other players see both in flight and the blasts.
- The AH-64D Apache flies as a helicopter. The collective (R and F) sets the main rotor's lift: about half lifts it off, and more climbs. The stick tilts it (centred, it levels itself) and Q and E turn it in the hover; at speed it turns with its bank. The rotor spins up from a runway start and runs down when a flight ends, and its lift grows near the ground and with forward speed. Level flight tops out near 150 kt.
- A runway start puts the Apache on the heliport beside the heavy apron: ten marked and lit pads, 170 m apart. It takes the first pad free of other players (and of the two parked Apaches), so helicopters starting together never pile up.
- V opens the Apache's TADS sight: the camera sits at the sight turret in the nose, which turns with it, and stays on the ground point it is pointed at. The mouse or arrows slew it, scroll zooms, and Y switches TV and IR. 1–4 pick the M230, the Hellfires, the Hydra rockets or the Stingers; Space or a click fires.
  - M230: its turret follows the sight within its limits (±86° across, +11° to −60°), and the rounds leave along the barrel.
  - Hellfires (the model's own eight): they ride the sight's laser spot onto the target, out to 8 km.
  - Hydra 70: fired along the nose from the two 19-tube pods, whose rockets disappear one by one.
  - Stingers (four, on the wingtips): heat-seekers for aircraft ahead.
  - Outside the sight, Space fires the gun ahead and X the picked store. Other players see the rotors, sights, gun, the remaining Hellfires, and the missiles and rockets in flight.
- Every F-22A store rides inside, and the bay doors open as each one goes. There are two loadouts:
  - Air superiority: 6 × AIM-120C in the main bay and 2 × AIM-9X in the side bays.
  - Precision strike: 2 × GBU-32 JDAM.
- Releasing a GBU-32 (X) hands you its seeker camera. The crosshair is where it will hit; steer with the stick or the mouse, within the load its fins can make at its speed. The jet flies hands-off meanwhile. C hands control back to the jet; X releases the next bomb, which takes over the camera. Control also returns to the jet on impact, if the jet is hit, or if it gets low and sinking. Other players see the bomb fly and the blast.
- After a nuclear bomb is dropped, that bomb needs to cool down before the next one: B61 2 minutes; the B-2's B83s 4 minutes, counted from when the last of the sixteen is dropped.
- With other players online, Rebuild city starts a vote (Y votes yes). The city is rebuilt for everyone when at least 2/3 of the players vote yes.


## The city

- The city is zoned. A downtown of towers and supertalls is ringed by shopping and office streets, which also run along the avenues. Apartment districts come next (some built around courtyards), then suburbs of houses on lawns, then fields at the edge. Industrial belts of warehouses, tank farms and container yards follow the river and the south edge. There is a central park beside downtown, about twenty other big parks, a green belt along the river, plazas, and surface parking.
- Buildings have styles: house, apartment block, office tower, shop, hotel, warehouse, parking garage and civic building. Each style has its own windows and ground floor. Rooftops carry stair and lift houses, air-conditioning plant, water tanks, antennas, dishes, solar panels and the odd billboard, and houses have pitched roofs. Rooftop pieces disappear when their building is damaged and come back when the city is rebuilt.
- Streets have kerbs, sidewalks and lane markings by type:
  - avenues: a planted median, three lanes each way and parking bays;
  - streets: a dashed centre line, two lanes and parking bays;
  - lanes: one lane each way.
- Crossings carry zebra stripes and stop lines. Some avenue crossings are roundabouts. Other street crossings have traffic signals on a 24 s cycle.
- Traffic keeps right in its lanes, stops and queues at red lights, and goes round the roundabouts. It runs mostly in the busy districts around wherever you are.
- At night, street lamps light pools on the ground (warm in residential streets, white downtown and in the shopping streets, sodium orange in industry). Parking lots, yards, plazas, park paths and bridges have their own lights. Lit shopfronts and signs (some animated), floodlit warehouses and civic buildings, lit garage decks and hotel lobbies add to the windows. Cars show head and tail lights, tall buildings carry red aviation lights, and signal heads change colour. From altitude the districts stay recognisable: downtown and the shopping streets bright, suburbs warm and sparse, industry orange, parks dark.
- The building layout is identical on every machine and graphics setting, so collisions and shared damage match in multiplayer. The graphics settings only change how many trees and parked cars there are, how far detail is drawn and how it is rendered (see Graphics and performance).

## Graphics and performance

The Graphics panel (start screen, pause screen, or the GRAPHICS button) holds every display option. They are saved on the device. None of them touches the flight model, the weapons, collisions or what is sent to other players: the simulation runs in fixed 1/120 s steps on every device, and keeps real time down to 12 FPS.

- **Presets**: Ultra low, Low, Medium, High, Ultra. A preset fills in every option below; changing any one of them makes the preset Custom. On the first visit the game picks a preset from what the browser reports about the device (GPU name, memory, cores, touch); Auto-detect picks it again, and Reset to defaults restores everything.
- **Render distance** (6 to 26 km): where the haze closes in. Forests, street furniture, rooftop detail, traffic and parked aircraft are drawn out to distances that follow it, and the weather can still bring the haze closer.
- **Resolution** (50 to 150% of the display's own resolution).
- **Shadows**: off, or a 512 to 4096 px shadow map.
- **Effects**: the share of smoke, fire, dust and rain that is drawn; bloom from High up (desktop only).
- **Textures**: the largest size aircraft textures are loaded at (512 px to full size; on the next load) and the anisotropic filtering of ground and marking textures (at once).
- **Environment detail**: forest and cloud density and how far aircraft keep their full models (at once); the city's trees, parked cars and traffic, and the terrain mesh's resolution (on the next load). The buildings never change.
- **Anti-aliasing** (MSAA; on the next load) and a **frame rate limit** (30 or 60 FPS). Browsers always synchronise drawing with the display, so there is no VSync switch to turn off.
- **Auto-optimise** (on by default): if the frame rate stays under about 26 FPS on weak hardware (38 or 48 where the device has more headroom) for 8 seconds of flying, it trims one step of optional visuals: resolution first, then bloom, shadows, effects and distance. Twenty good seconds give a step back; a step back that does not hold is not retried for a minute, then two, four and so on. It never changes saved settings, and changing any setting yourself clears what it trimmed.
- **FPS counter** and a **performance overlay**: frame rate, frame time and the worst recent frame, script time per frame, preset, render distance, resolution, draw calls, triangles, and the JavaScript heap where the browser reports it. Browsers do not report CPU load, GPU load or video memory to a page, and the overlay says so rather than guessing.

What keeps the frame rate up:

- Forest chunks and city detail tiles are culled against the view as well as by distance, and far forest thins out toward the edge of its range. The buildings are skipped once the haze has swallowed the city.
- Aircraft models load when first needed (your own, another player's, the ones parked nearby) instead of all twelve up front. On High and Ultra the rest follow in the background.
- Parked aircraft and distant players' aircraft are drawn from shared, merged copies of the model with two thinner levels of detail. The copy still takes hits, locks and missiles at any distance, and a damaged aircraft always shows its full model.
- Traffic sends the GPU only the cars that are drawn, and stops altogether when the city is out of sight.
- Changing aircraft or repairing one frees the old airframe's geometry, and a player who leaves frees theirs.
