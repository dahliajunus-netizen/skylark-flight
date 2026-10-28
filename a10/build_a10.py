# Fairchild Republic A-10C Thunderbolt II for Skylark: 16.26 m long, 17.53 m span, 4.47 m tall.
# Run headless:  blender --background --python a10/build_a10.py -- A10.gltf.json
#
# Blender axes: nose toward -Y, up +Z, the pilot's left wing on +X. The glTF export turns this into
# nose +Z, and the sim turns it again to nose -Z, so a point (bx, by, bz) here is (-bx, bz, by) in the sim.
# The origin is the centre of gravity; the wheels touch the ground at z = -GEAR.
# Part names follow the sim's rules: wheels and struts are the gear, "Stabilizer" pivots for pitch,
# Wing/Vertical Tail/Stabilizer are damage zones, and Nacelle/Fan Face/Exhaust Cone/Engine Pylon are the engine pods.
import bpy, bmesh, math, sys, json, os, base64, shutil, tempfile

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'A10.gltf.json'
GEAR = 2.05

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root = bpy.data.objects.new('A-10C', None)
scene.collection.objects.link(root)


# ---------------- materials ----------------
def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def material(name, hexc, metal=0.15, rough=0.55, alpha=1.0):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    rgb = [lin(int(hexc[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    b.inputs['Base Color'].default_value = (*rgb, 1.0)
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if alpha < 1:
        b.inputs['Alpha'].default_value = alpha
        m.surface_render_method = 'BLENDED'
    return m

GREY = material('Warthog Grey', '#555b60')
GREY_D = material('Warthog Grey Dark', '#43484c')
GLASS = material('Canopy', '#3a3d2c', 0.6, 0.06, 0.82)
FRAME = material('Canopy Frame', '#3f4447', 0.2, 0.5)
INTAKE = material('Intake Dark', '#0d0e10', 0.0, 0.8)
METAL = material('Nozzle Metal', '#4d4842', 0.85, 0.35)
GUN = material('Gun Metal', '#2c2e30', 0.8, 0.35)
STRUT = material('Gear Strut', '#c8cacd', 0.6, 0.3)
TIRE = material('Tire', '#1c1c1c', 0.0, 0.85)


# ---------------- mesh helpers ----------------
def make(name, parts, mat, smooth=True, origin=None):
    """parts: list of (verts, faces) merged into one mesh object."""
    verts, faces = [], []
    for v, f in parts:
        o = len(verts)
        verts += v
        faces += [tuple(i + o for i in face) for face in f]
    if origin:
        verts = [(x - origin[0], y - origin[1], z - origin[2]) for x, y, z in verts]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(38))
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.parent = root
    if origin:
        ob.location = origin
    return ob

def loft(rings, cap0=True, cap1=True):
    n = len(rings[0])
    verts = [v for r in rings for v in r]
    faces = []
    for i in range(len(rings) - 1):
        for j in range(n):
            a, b = i * n + j, i * n + (j + 1) % n
            faces.append((a, b, b + n, a + n))
    if cap0:
        faces.append(tuple(reversed(range(n))))
    if cap1:
        faces.append(tuple(range((len(rings) - 1) * n, len(rings) * n)))
    return verts, faces

def sgnpow(v, p):
    return math.copysign(abs(v) ** p, v)

def ring_y(y, w, h, zc, xc=0.0, n=24, p=2.0):
    """superellipse cross-section across x/z at station y (p > 2 is boxier)."""
    e = 2.0 / p
    return [(xc + w * sgnpow(math.cos(a), e), y, zc + h * sgnpow(math.sin(a), e))
            for a in (2 * math.pi * k / n for k in range(n))]

def ring_x(x, r, yc, zc, n=20):
    return [(x, yc + r * math.cos(a), zc + r * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))]

def foil(t, n=12):
    """closed NACA 00xx outline as (chordwise 0..1, thickness offset), TE -> upper -> LE -> lower -> TE."""
    yt = lambda x: 5 * t * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1015 * x ** 4)
    xs = [(1 - math.cos(math.pi * k / n)) / 2 for k in range(n + 1)]
    return [(x, yt(x)) for x in reversed(xs)] + [(x, -yt(x)) for x in xs[1:-1]]

def span_section(x, le, chord, zc, t, sx=1):
    """airfoil at span station x (wing and tailplane), chord along +y."""
    return [(sx * x, le + c * chord, zc + u * chord) for c, u in foil(t)]

def fin_section(z, le, chord, xc, t):
    """airfoil at height z (vertical tails), thickness across x."""
    return [(xc + u * chord, le + c * chord, z) for c, u in foil(t)]

def box(x0, x1, y0, y1, z0, z1):
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, f

def cyl_z(x, y, z0, z1, r, n=12):
    return loft([[(x + r * math.cos(a), y + r * math.sin(a), z) for a in (2 * math.pi * k / n for k in range(n))] for z in (z0, z1)])

def wheel(x, y, zc, r, w, n=22):
    hub = r * 0.55
    rings = [ring_x(x - w / 2, hub, y, zc, n), ring_x(x - w / 2, r * 0.92, y, zc, n), ring_x(x - w * 0.4, r, y, zc, n),
             ring_x(x + w * 0.4, r, y, zc, n), ring_x(x + w / 2, r * 0.92, y, zc, n), ring_x(x + w / 2, hub, y, zc, n)]
    return loft(rings)


# ---------------- fuselage ----------------
# station y, half-width, half-height, centre z, boxiness
FUS = [(-8.12, 0.05, 0.05, -0.18, 2.0), (-7.95, 0.34, 0.32, -0.14, 2.2), (-7.4, 0.55, 0.58, -0.04, 2.4),
       (-6.6, 0.7, 0.8, 0.06, 2.6), (-5.6, 0.78, 0.94, 0.14, 2.8), (-4.4, 0.8, 0.98, 0.12, 3.0),
       (-3.0, 0.82, 0.94, 0.06, 3.0), (-1.0, 0.8, 0.88, 0.0, 3.0), (1.5, 0.76, 0.8, 0.02, 3.0),
       (3.4, 0.66, 0.7, 0.08, 2.8), (5.2, 0.48, 0.55, 0.18, 2.6), (6.8, 0.3, 0.38, 0.3, 2.4),
       (7.9, 0.16, 0.22, 0.38, 2.2), (8.14, 0.04, 0.06, 0.42, 2.0)]
make('Fuselage', [loft([ring_y(y, w, h, zc, p=p) for y, w, h, zc, p in FUS])], GREY)

# bubble canopy over the cockpit, with its frame and the windscreen bow
CAN = [(-6.0, 0.08, 0.06, 1.0), (-5.6, 0.38, 0.42, 1.0), (-5.0, 0.48, 0.62, 1.0),
       (-4.3, 0.49, 0.66, 1.0), (-3.7, 0.4, 0.52, 1.0), (-3.2, 0.06, 0.1, 1.0)]
make('Canopy', [loft([ring_y(y, w, h, zc, n=28) for y, w, h, zc in CAN])], GLASS)
bow = lambda y, w, h, zc: loft([ring_y(y - 0.04, w + 0.015, h + 0.015, zc, n=28), ring_y(y + 0.04, w + 0.015, h + 0.015, zc, n=28)], False, False)
make('Windscreen Frame', [bow(-5.42, 0.42, 0.5, 1.0)], FRAME)
make('Canopy Frame', [bow(-4.72, 0.485, 0.645, 1.0)], FRAME)
# dorsal hump behind the canopy, blending into the fuselage spine
make('Dorsal Fairing', [loft([ring_y(y, w, h, zc) for y, w, h, zc in
     [(-3.5, 0.05, 0.05, 1.0), (-3.1, 0.34, 0.3, 0.98), (-1.0, 0.38, 0.22, 0.86), (1.5, 0.32, 0.14, 0.8), (3.0, 0.05, 0.05, 0.74)]])], GREY)

# GAU-8/A Avenger: seven barrels in a cluster poking out under the nose
barrels = [loft([ring_y(y, 0.026, 0.026, -0.2 + 0.075 * math.sin(a), 0.075 * math.cos(a), n=8) for y in (-8.62, -7.9)])
           for a in (2 * math.pi * k / 7 for k in range(7))]
barrels.append(loft([ring_y(y, 0.125, 0.125, -0.2, n=16) for y in (-8.2, -8.12, -7.7)]))
make('GAU-8 Barrels', barrels, GUN)


# ---------------- wings ----------------
DIH = math.tan(math.radians(7))
def wing_stations():
    # span x, leading edge y, chord, centre z, thickness/chord
    return [(0.55, -0.9, 3.0, -0.45, 0.16), (3.3, -0.9, 3.0, -0.45, 0.16),
            (8.5, -0.56, 1.98, -0.45 + 5.2 * DIH, 0.13), (8.77, -0.46, 1.72, -0.45 + 5.2 * DIH - 0.14, 0.07)]
def wing_at(x):
    st = wing_stations()[:3]
    for (x0, *a), (x1, *b) in zip(st, st[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            return [p + (q - p) * f for p, q in zip(a, b)]
    raise ValueError(x)

for sx, side in ((1, 'L'), (-1, 'R')):
    make('Wing.' + side, [loft([span_section(x, le, c, zc, t, sx) for x, le, c, zc, t in wing_stations()])], GREY)
    # main gear pods under the wing, where the wheels fold forward
    make('Gear Pod.' + side, [loft([ring_y(y, w, h, zc, sx * 2.6, n=18) for y, w, h, zc in
         [(-2.15, 0.04, 0.04, -0.72), (-1.85, 0.24, 0.26, -0.72), (-1.2, 0.33, 0.36, -0.73), (0.6, 0.33, 0.36, -0.73),
          (1.7, 0.22, 0.2, -0.66), (2.15, 0.04, 0.04, -0.6)]])], GREY)

# ---------------- tail ----------------
TAIL_Z = 0.55
for sx, side in ((1, 'L'), (-1, 'R')):
    st = [(0.2, 6.2, 1.75, 0.1), (2.9, 6.45, 1.42, 0.09)]
    make('Stabilizer.' + side, [loft([span_section(x, le, c, TAIL_Z, t, sx) for x, le, c, t in st])], GREY,
         origin=(sx * 0.2, 6.9, TAIL_Z))
    # twin fins on the tailplane tips, mostly above it
    fx = sx * 2.92
    make('Vertical Tail.' + side, [loft([fin_section(z, le, c, fx, t) for z, le, c, t in
         [(-0.55, 6.32, 1.55, 0.08), (-0.2, 6.2, 1.75, 0.1), (2.15, 6.3, 1.65, 0.09), (2.42, 6.55, 1.2, 0.05)]])], GREY_D)

# ---------------- engines ----------------
ENG_X, ENG_Z = 1.6, 1.38
for sx, side in ((1, 'L'), (-1, 'R')):
    ex = sx * ENG_X
    # open intake: the lip turns inward to a fan face set back inside, and the pod ends in an open nozzle
    make('Nacelle.' + side, [loft([ring_y(y, r, r, ENG_Z, ex, n=28) for y, r in
         [(2.9, 0.53), (2.5, 0.56), (2.42, 0.6), (2.48, 0.66), (2.75, 0.7), (3.6, 0.7), (4.8, 0.66), (5.6, 0.56),
          (6.0, 0.46), (5.9, 0.42)]], False, False)], GREY_D)
    make('Fan Face.' + side, [loft([ring_y(y, r, r, ENG_Z, ex, n=28) for y, r in [(2.86, 0.535), (2.9, 0.535)]]),
                              loft([ring_y(y, r, r, ENG_Z, ex, n=12) for y, r in [(2.62, 0.02), (2.86, 0.17)]])], INTAKE)
    make('Exhaust Cone.' + side, [loft([ring_y(y, r, r, ENG_Z, ex, n=16) for y, r in [(5.86, 0.43), (5.9, 0.43)]]),
                                  loft([ring_y(y, r, r, ENG_Z, ex, n=16) for y, r in [(5.9, 0.34), (6.35, 0.06)]])], METAL)
    # short pylon from the rear fuselage up to the pod
    x0, x1 = sorted((sx * 0.25, sx * (ENG_X - 0.2)))
    make('Engine Pylon.' + side, [box(x0, x1, 3.2, 5.1, 0.55, ENG_Z - 0.45)], GREY_D, smooth=False)

# ---------------- landing gear ----------------
MAIN_X, MAIN_Y, MAIN_R = 2.6, 0.25, 0.5
NOSE_X, NOSE_Y, NOSE_R = -0.36, -5.5, 0.38   # offset right of the centreline to make room for the gun
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Main Gear Strut.' + side, [cyl_z(sx * (MAIN_X - 0.2), MAIN_Y, -GEAR + MAIN_R, -0.75, 0.09),
                                     box(sx * (MAIN_X - 0.22) - 0.05, sx * (MAIN_X - 0.22) + 0.05, MAIN_Y - 0.06, MAIN_Y + 0.06, -GEAR + MAIN_R - 0.06, -GEAR + MAIN_R + 0.06)], STRUT)
    make('Main Wheel.' + side, [wheel(sx * MAIN_X, MAIN_Y, -GEAR + MAIN_R, MAIN_R, 0.3)], TIRE)
make('Nose Gear Strut', [cyl_z(NOSE_X, NOSE_Y, -GEAR + NOSE_R, -0.7, 0.075)], STRUT)
make('Nose Wheel', [wheel(NOSE_X, NOSE_Y, -GEAR + NOSE_R, NOSE_R, 0.22)], TIRE)

# ---------------- pylons and bomb stations ----------------
# eight Mk-82s: three under each outer wing and one inboard of each gear pod (nose -Y, like the sim's bombs)
STATIONS = [6.6, 5.5, 4.4, 1.55]
bombs = []
for sx, side in ((1, 'L'), (-1, 'R')):
    for i, x in enumerate(STATIONS):
        le, c, zc, t = wing_at(x)
        under = zc - 0.5 * t * c * 0.96
        y0 = le + 0.12 * c
        make('Wing Pylon %d.%s' % (i + 1, side), [box(sx * x - 0.05, sx * x + 0.05, y0, y0 + 1.15, under - 0.2, under + 0.05)], GREY_D, smooth=False)
        bombs.append((sx * x, y0 + 0.62, under - 0.2 - 0.19))

# ---------------- export ----------------
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='SELECT')
# this exporter only writes .gltf + .bin, so write those to a temp folder and fold the buffer into one JSON file
tmp = tempfile.mkdtemp()
bpy.ops.export_scene.gltf(filepath=os.path.join(tmp, 'a10.gltf'), export_format='GLTF_SEPARATE', use_selection=False,
                          export_yup=True, export_apply=True, export_texcoords=False, export_animations=False,
                          export_cameras=False, export_lights=False)
with open(os.path.join(tmp, 'a10.gltf')) as f:
    gltf = json.load(f)
for b in gltf['buffers']:
    with open(os.path.join(tmp, b['uri']), 'rb') as f:
        b['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(f.read()).decode()
with open(OUT, 'w') as f:
    json.dump(gltf, f, separators=(',', ':'))
shutil.rmtree(tmp)

# release order alternates sides, outboard first, in sim coordinates (x right, y up, z aft)
order = [b for pair in zip(bombs[:4], bombs[4:]) for b in pair]
sim = lambda p: [round(-p[0], 3), round(p[2], 3), round(p[1], 3)]
print('RIG_BOMBS ' + json.dumps([sim(b) for b in order]))
print('MESHES %d  TRIS %d' % (sum(o.type == 'MESH' for o in scene.objects),
                              sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')))
