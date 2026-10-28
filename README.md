# Skylark

A browser flight simulator: fly an F-15C, a Eurofighter Typhoon, an A-10C Thunderbolt II, a Boeing 757-200, a Boeing 747-8 or a B-52H from an island airbase over a destructible city.
Open `index.html` through any static web server. All six aircraft models (`*.gltf.json`) were built in Blender; the A-10 and 747-8 rebuild with `blender --background --python a10/build_a10.py -- A10.gltf.json` and `blender --background --python b747/build_b747.py -- B747.gltf.json`.
