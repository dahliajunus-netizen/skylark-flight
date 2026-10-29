# Skylark

A browser flight simulator: fly an F-15C, a Eurofighter Typhoon, an A-10C Thunderbolt II, a Boeing 757-200, a Boeing 747-8, a B-52H or an AC-130J Ghostrider gunship from a huge military airbase next to a destructible city.
Open `index.html` through any static web server. All seven aircraft models (`*.gltf.json`) were built in Blender; the A-10, 747-8 and AC-130J rebuild with `blender --background --python a10/build_a10.py -- A10.gltf.json`, `blender --background --python b747/build_b747.py -- B747.gltf.json` and `blender --background --python ac130/build_ac130.py -- AC130.gltf.json`.

## Multiplayer

Everyone who has the page open flies in the same world under a callsign picked on the first visit (click the player count to change it). There is no server: the pages connect to each other directly over WebRTC with [Trystero](https://github.com/dmotz/trystero), finding each other through public Nostr relays. Players whose networks block direct connections (mobile data, school or office Wi-Fi) go through a Metered TURN relay; its API key is in the page, so its usage limit is set in Metered. Players see each other's aircraft with name tags. Bomb, shell and crash blasts, cannon hits and nuclear blasts happen in everyone's copy of the city. A player who joins late catches up on the damage from someone already there.

- Cannon rounds, bombs and shells hit other players' aircraft. A hit tears off the part it lands on (shoot the right wing and the right wing comes off, cut at the point hit), as flying into a building does. Enough hits on the fuselage, or a close blast, bring the aircraft down, and everyone sees who shot whom.
- Air-to-air missiles are a separate loadout on the F-15C (4 × AIM-120C, 4 × AIM-9X), Typhoon (4 × AIM-120C, 2 × IRIS-T) and A-10 (2 × AIM-9X). The radar (APG-63, CAPTOR; on the A-10 a 20 km targeting pod) shows other players in a cone ahead; L locks and cycles, X fires. The heat-seeker is used inside 15 km, the AIM-120 beyond (out to 50 km). Missiles steer by proportional navigation with limited g, and their proximity burst tears parts off like any blast. Targets get LOCKED and MISSILE warnings.
- Only one player at a time can fly the B-52.
- After a nuclear bomb is dropped, that bomb needs to cool down before the next one: B61 2 minutes, B28 4 minutes, B41 8 minutes.
- With other players online, Rebuild city starts a vote (Y votes yes). The city is rebuilt for everyone when at least 2/3 of the players vote yes.
