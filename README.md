# Skylark

A browser flight simulator: fly an F-15C, a Eurofighter Typhoon, an A-10C Thunderbolt II, a Boeing 757-200, a Boeing 747-8, a B-52H or an AC-130J Ghostrider gunship from a huge military airbase next to a destructible city.
Open `index.html` through any static web server. All seven aircraft models (`*.gltf.json`) were built in Blender; the A-10, 747-8 and AC-130J rebuild with `blender --background --python a10/build_a10.py -- A10.gltf.json`, `blender --background --python b747/build_b747.py -- B747.gltf.json` and `blender --background --python ac130/build_ac130.py -- AC130.gltf.json`.
