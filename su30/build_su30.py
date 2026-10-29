# Sukhoi Su-30SM for Skylark: 21.935 m long, 14.7 m span, 6.36 m tall (the-blueprints.com Su-30SM sheet), two-seat,
# canards, twin AL-31FP engines with thrust-vectoring nozzles.
# Run headless:  blender --background --python su30/build_su30.py -- SU30.gltf.json
#
# Blender axes: nose toward -Y, up +Z, the pilot's left wing on +X. The glTF export turns this into
# nose +Z, and the sim turns it again to nose -Z, so a point (bx, by, bz) here is (-bx, bz, by) in the sim.
# The origin is the centre of gravity; the wheels touch the ground at z = -GEAR.
# Part names follow the sim's rules: wheels and struts are the gear, "Stabilator" and "Canard" pivot for pitch,
# "Vectoring Nozzle" pivots with the pitch input, Wing/Vertical Tail/Stabilator/Canard are damage zones.
import bpy, bmesh, math, sys, json, os, base64, shutil, tempfile

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'SU30.gltf.json'
GEAR = 2.4

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root = bpy.data.objects.new('Su-30SM', None)
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

BLUE = material('Flanker Blue Grey', '#56657a', 0.15, 0.55)
BLUE_D = material('Flanker Blue Grey Dark', '#46546a', 0.15, 0.55)
LIGHT = material('Flanker Light Grey', '#9aa3ad', 0.15, 0.55)
RADOME = material('Radome', '#c9ccce', 0.0, 0.45)
GLASS = material('Canopy', '#3d4048', 0.6, 0.06, 0.8)
FRAME = material('Canopy Frame', '#3b4553', 0.2, 0.5)
INTAKE = material('Intake Dark', '#0e1012', 0.0, 0.8)
METAL = material('Nozzle Metal', '#5a5550', 0.85, 0.35)
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

def loft(rings, cap0=True, cap1=True, closed=True):
    n = len(rings[0])
    verts = [v for r in rings for v in r]
    faces = []
    for i in range(len(rings) - 1):
        for j in range(n if closed else n - 1):
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

def arc_y(y, w, h, zc, a0, a1, n=8, grow=1.012):
    """part of an elliptical section (angles in degrees, 0 = +x, 90 = top), just proud of the skin: livery bands."""
    return [(w * grow * math.cos(a), y, zc + h * grow * math.sin(a))
            for a in (math.radians(a0 + (a1 - a0) * k / (n - 1)) for k in range(n))]

def ring_x(x, r, yc, zc, n=20):
    return [(x, yc + r * math.cos(a), zc + r * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))]

def foil(t, n=12):
    """closed NACA 00xx outline as (chordwise 0..1, thickness offset), TE -> upper -> LE -> lower -> TE."""
    yt = lambda x: 5 * t * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1015 * x ** 4)
    xs = [(1 - math.cos(math.pi * k / n)) / 2 for k in range(n + 1)]
    return [(x, yt(x)) for x in reversed(xs)] + [(x, -yt(x)) for x in xs[1:-1]]

def span_section(x, le, chord, zc, t, sx=1):
    return [(sx * x, le + c * chord, zc + u * chord) for c, u in foil(t)]

def fin_section(z, le, chord, xc, t):
    return [(xc + u * chord, le + c * chord, z) for c, u in foil(t)]

def box(x0, x1, y0, y1, z0, z1):
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return v, f

def cyl_z(x, y, z0, z1, r, n=12):
    return loft([[(x + r * math.cos(a), y + r * math.sin(a), z) for a in (2 * math.pi * k / n for k in range(n))] for z in (z0, z1)])

def cyl_y(x, z, y0, y1, r, n=10):
    return loft([[(x + r * math.cos(a), y, z + r * math.sin(a)) for a in (2 * math.pi * k / n for k in range(n))] for y in (y0, y1)])

def wheel(x, y, zc, r, w, n=22):
    hub = r * 0.55
    rings = [ring_x(x - w / 2, hub, y, zc, n), ring_x(x - w / 2, r * 0.92, y, zc, n), ring_x(x - w * 0.4, r, y, zc, n),
             ring_x(x + w * 0.4, r, y, zc, n), ring_x(x + w / 2, r * 0.92, y, zc, n), ring_x(x + w / 2, hub, y, zc, n)]
    return loft(rings)

def interp(table, y):
    """linear interpolation in a table of (y, *values) rows."""
    for a, b in zip(table, table[1:]):
        if a[0] <= y <= b[0]:
            f = (y - a[0]) / (b[0] - a[0])
            return [p + (q - p) * f for p, q in zip(a[1:], b[1:])]
    return list((table[0] if y < table[0][0] else table[-1])[1:])





# ---------------- fuselage: the raised cockpit spine and the flat lifting body between the engines ----------------
# station y, half-width, half-height, centre z
NOSE = [(-11.0, 0.05, 0.05, -0.05), (-10.3, 0.33, 0.33, 0.0), (-9.3, 0.52, 0.53, 0.05), (-8.5, 0.62, 0.64, 0.08)]
SPINE = [(-8.5, 0.62, 0.64, 0.08), (-7.2, 0.74, 0.76, 0.12), (-5.6, 0.8, 0.82, 0.14), (-3.8, 0.82, 0.76, 0.1),
         (-1.5, 0.8, 0.62, 0.08), (1.5, 0.7, 0.5, 0.12), (4.5, 0.55, 0.42, 0.18), (7.5, 0.42, 0.36, 0.22),
         (9.8, 0.3, 0.28, 0.25), (10.9, 0.12, 0.12, 0.28), (11.0, 0.03, 0.03, 0.28)]
make('Radome', [loft([ring_y(y, w, h, zc, n=24) for y, w, h, zc in NOSE], True, False)], RADOME)
make('Fuselage', [loft([ring_y(y, w, h, zc, n=24, p=2.3) for y, w, h, zc in SPINE], False, True)], BLUE)
# the flat, wide centre body that blends the spine into the wing roots and carries the engines
make('Centre Body', [loft([ring_y(y, w, h, zc, n=24, p=3.2) for y, w, h, zc in
     [(-4.6, 0.85, 0.2, -0.05), (-3.0, 2.25, 0.32, -0.12), (0.0, 2.45, 0.36, -0.15), (4.5, 2.4, 0.34, -0.12),
      (7.4, 2.3, 0.28, -0.08), (8.4, 1.0, 0.18, 0.0)]])], BLUE)
# tandem two-seat canopy and its frames
CAN = [(-7.6, 0.08, 0.06, 0.62), (-7.0, 0.42, 0.42, 0.68), (-6.0, 0.5, 0.58, 0.7), (-4.8, 0.5, 0.6, 0.7),
       (-3.7, 0.42, 0.48, 0.68), (-2.9, 0.06, 0.08, 0.62)]
make('Canopy', [loft([ring_y(y, w, h, zc, n=28) for y, w, h, zc in CAN])], GLASS)
bow = lambda y, w, h, zc: loft([ring_y(y - 0.04, w + 0.015, h + 0.015, zc, n=28), ring_y(y + 0.04, w + 0.015, h + 0.015, zc, n=28)], False, False)
make('Windscreen Frame', [bow(-6.9, 0.44, 0.45, 0.68)], FRAME)
make('Canopy Frame', [bow(-5.35, 0.505, 0.6, 0.7), bow(-3.9, 0.44, 0.5, 0.68)], FRAME)
# the infrared search-and-track ball ahead of the windscreen, offset to the right
make('IRST', [loft([ring_y(-7.95 + 0.22 * math.cos(a), 0.22 * math.sin(a) + 0.01, 0.22 * math.sin(a) + 0.01, 0.78, -0.25, n=12)
                    for a in [math.pi * k / 8 for k in range(9)]])], GLASS)

# ---------------- wings: LERX blending into a 42° swept wing with slight anhedral ----------------
ANH = math.tan(math.radians(2.5))
def wz(x):
    return -0.05 - max(0.0, x - 2.3) * ANH
# span x, leading edge y, chord, thickness/chord
WING = [(1.0, -7.2, 12.0, 0.05), (2.3, -4.2, 9.1, 0.05), (2.9, -1.7, 6.7, 0.05), (7.2, 1.95, 1.75, 0.04), (7.35, 2.05, 1.55, 0.035)]
def wing_at(x):
    le, c, t = interp([(s[0], s[1], s[2], s[3]) for s in WING], x)
    return le, c, wz(x), t
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Wing.' + side, [loft([span_section(x, le, c, wz(x), t, sx) for x, le, c, t in WING])], BLUE)
    le, c, z, t = wing_at(7.35)
    # wingtip launch rail (the R-73s ride on it)
    make('Wing Tip Rail.' + side, [loft([ring_y(y, 0.07, 0.07, z - 0.05, sx * 7.42, n=10) for y in (le - 1.6, le + 1.9)])], BLUE_D)
    # canards on the sides of the cockpit, pivoting for pitch
    make('Canard.' + side, [loft([span_section(x, le_, ch, 0.32, 0.05, sx) for x, le_, ch in [(0.75, -6.4, 1.7), (3.05, -5.05, 0.65)]])], BLUE,
         origin=(sx * 0.9, -5.6, 0.32))

# ---------------- engines: intakes under the wing roots, wide-spaced nacelles, thrust-vectoring nozzles ----------------
ENG_X, ENG_Z = 1.55, -0.72
for sx, side in ((1, 'L'), (-1, 'R')):
    x = sx * ENG_X
    make('Intake.' + side, [loft([ring_y(y, w, h, zc, x, n=20, p=4.0) for y, w, h, zc in
         [(-3.3, 0.6, 0.66, ENG_Z - 0.05), (-3.1, 0.66, 0.74, ENG_Z - 0.05), (-1.5, 0.66, 0.76, ENG_Z), (0.5, 0.64, 0.7, ENG_Z + 0.05)]], False, False)], BLUE_D)
    make('Intake Face.' + side, [loft([ring_y(y, 0.58, 0.65, ENG_Z - 0.05, x, n=20, p=4.0) for y in (-2.85, -2.82)])], INTAKE)
    make('Engine Bay.' + side, [loft([ring_y(y, r, r * 1.05, ENG_Z + 0.1 + 0.02 * (y - 0.5), x, n=20, p=2.2) for y, r in
         [(0.5, 0.64), (3.5, 0.66), (6.5, 0.62), (8.6, 0.58), (8.95, 0.56)]], False, False)], LIGHT)
    # the nozzle turns on its hinge at the end of the engine bay
    hinge = (x, 8.95, ENG_Z + 0.27)
    make('Vectoring Nozzle.' + side, [loft([ring_y(y, r, r, hinge[2], x, n=24) for y, r in
         [(8.95, 0.55), (9.6, 0.56), (10.2, 0.52), (10.15, 0.46)]], False, False),
         loft([ring_y(y, r, r, hinge[2], x, n=16) for y, r in [(9.1, 0.42), (9.3, 0.42)]])], METAL, origin=hinge)
    # tail booms outboard of the engines carry the fins and stabilators
    bx = sx * 2.45
    make('Tail Boom.' + side, [loft([ring_y(y, w, h, 0.0, bx, n=14) for y, w, h in
         [(4.0, 0.06, 0.06), (5.0, 0.28, 0.24), (9.6, 0.24, 0.2), (10.4, 0.05, 0.05)]])], BLUE)
    make('Vertical Tail.' + side, [loft([fin_section(z, le_, ch, bx, t) for z, le_, ch, t in
         [(0.15, 4.95, 3.5, 0.05), (0.6, 5.25, 3.25, 0.05), (3.6, 7.65, 1.45, 0.045), (3.76, 7.85, 1.2, 0.03)]])], BLUE)
    make('Ventral Fin.' + side, [loft([fin_section(z, le_, ch, bx, 0.06) for z, le_, ch in [(-0.1, 6.0, 2.4), (-0.95, 7.1, 1.1)]])], BLUE_D)
    make('Stabilator.' + side, [loft([span_section(xx, le_, ch, 0.0, 0.045, sx) for xx, le_, ch in [(2.55, 6.4, 3.1), (4.35, 8.15, 1.25)]])], BLUE,
         origin=(sx * 2.6, 7.7, 0.0))

# ---------------- landing gear: twin nose wheels, single main wheels on long legs ----------------
R_MAIN, W_MAIN, R_NOSE = 0.56, 0.32, 0.34
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Main Gear Strut.' + side, [cyl_z(sx * 2.15, 1.5, -GEAR + R_MAIN, -0.55, 0.1),
                                     cyl_y(sx * 2.15, -GEAR + R_MAIN, 1.45, 1.55, 0.08)], STRUT)
    make('Main Wheel.' + side, [wheel(sx * 2.35, 1.5, -GEAR + R_MAIN, R_MAIN, W_MAIN)], TIRE)
NOSE_Y = -6.6
make('Nose Gear Strut', [cyl_z(0, NOSE_Y, -GEAR + R_NOSE, -0.55, 0.08), cyl_y(0, -GEAR + R_NOSE, NOSE_Y - 0.05, NOSE_Y + 0.05, 0.07)], STRUT)
make('Nose Wheel a', [wheel(0.2, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.18)], TIRE)
make('Nose Wheel b', [wheel(-0.2, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.18)], TIRE)


# ---------------- export ----------------
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='SELECT')
# this exporter only writes .gltf + .bin, so write those to a temp folder and fold the buffer into one JSON file
tmp = tempfile.mkdtemp()
bpy.ops.export_scene.gltf(filepath=os.path.join(tmp, 'su30.gltf'), export_format='GLTF_SEPARATE', use_selection=False,
                          export_yup=True, export_apply=True, export_texcoords=False, export_animations=False,
                          export_cameras=False, export_lights=False)
with open(os.path.join(tmp, 'su30.gltf')) as f:
    gltf = json.load(f)
for b in gltf['buffers']:
    with open(os.path.join(tmp, b['uri']), 'rb') as f:
        b['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(f.read()).decode()
with open(OUT, 'w') as f:
    json.dump(gltf, f, separators=(',', ':'))
shutil.rmtree(tmp)

# numbers the sim needs, in sim coordinates (x right, y up, z aft)
sim = lambda p: [round(-p[0], 2), round(p[2], 2), round(p[1], 2)]
for x in (3.1, 4.3, 5.5, 7.35):
    le, c, z, t = wing_at(x)
    print('WING x=%.2f  under %.2f  mid-chord y %.2f' % (x, z - 0.5 * t * c, le + 0.45 * c))
print('NOZZLE', sim((ENG_X, 10.15, ENG_Z + 0.27)), 'FIN_TOP 3.76')
print('MESHES %d  TRIS %d' % (sum(o.type == 'MESH' for o in scene.objects),
                              sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')))
