# Aérospatiale/BAC Concorde for Skylark: 61.66 m long, 25.6 m span, 12.2 m tall, ogival delta wing, four Rolls-Royce/
# SNECMA Olympus 593 in two paired nacelles, a nose that droops for takeoff and landing, elevons instead of a tailplane.
# Run headless:  blender --background --python concorde/build_concorde.py -- CONCORDE.gltf.json
#
# Blender axes: nose toward -Y, up +Z, the pilot's left wing on +X. The glTF export turns this into
# nose +Z, and the sim turns it again to nose -Z, so a point (bx, by, bz) here is (-bx, bz, by) in the sim.
# The origin is the centre of gravity, 37 m behind the nose tip; the wheels touch the ground at z = -GEAR.
# Distances along the aircraft are written as s, metres from the nose tip (y = s - CG).
# Part names follow the sim's rules: wheels and struts are the gear, "Elevon" surfaces move with pitch and roll,
# "Droop Nose" lowers with the gear, Wing/Vertical Tail/Engine Nacelle are damage zones.
import bpy, bmesh, math, sys, json, os, base64, shutil, tempfile

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'CONCORDE.gltf.json'
GEAR = 6.0
CG = 37.0

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root = bpy.data.objects.new('Concorde', None)
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


WHITE = material('Concorde White', '#f1f2ef', 0.1, 0.4)
UNDER = material('Underside Grey', '#dcdfe1', 0.1, 0.45)
WINDOW = material('Windows', '#1d2228', 0.5, 0.15)
PROBE = material('Probe', '#2a2c2e', 0.3, 0.5)
INTAKE = material('Intake Dark', '#0d0f11', 0.0, 0.85)
METAL = material('Nozzle Metal', '#77706a', 0.85, 0.35)
SOOT = material('Exhaust Inner', '#1a1715', 0.4, 0.7)
STRUT = material('Gear Strut', '#c9cbce', 0.6, 0.3)
TIRE = material('Tire', '#1c1c1c', 0.0, 0.85)

Y = lambda s: s - CG


# ---------------- fuselage: a slender tube, the droop nose ahead of the windscreen, a long tapering tail cone ----------------
# station s, half-width, half-height, centre z
NOSE = [(0.0, 0.03, 0.03, -0.55), (1.0, 0.22, 0.21, -0.5), (2.2, 0.46, 0.45, -0.4), (3.6, 0.72, 0.72, -0.28),
        (5.0, 0.94, 0.95, -0.16), (6.2, 1.12, 1.16, -0.07)]
BODY = [(6.2, 1.12, 1.16, -0.07), (7.4, 1.27, 1.36, -0.03), (9.0, 1.38, 1.54, 0.0), (11.0, 1.44, 1.64, 0.0),
        (44.0, 1.44, 1.64, 0.0), (48.0, 1.38, 1.56, 0.04), (52.0, 1.18, 1.32, 0.16), (55.5, 0.9, 0.98, 0.33),
        (58.5, 0.58, 0.6, 0.42), (60.8, 0.24, 0.24, 0.42), (61.66, 0.03, 0.03, 0.4)]
HINGE = (0.0, Y(6.2), -1.05)  # the droop nose pivots on its lower edge
make('Droop Nose', [loft([ring_y(Y(s), w, h, zc, n=28) for s, w, h, zc in NOSE], True, False)], WHITE, origin=HINGE)
make('Droop Nose Probe', [cyl_y(0, -0.55, Y(-0.6), Y(0.3), 0.03, n=8)], PROBE, origin=HINGE)
make('Fuselage', [loft([ring_y(Y(s), w, h, zc, n=28) for s, w, h, zc in BODY], False, True)], WHITE)

def body_at(s):
    return interp(BODY, s)

def strip(s0, s1, a0, a1, n=4):
    rings = []
    for s in (s0, s1):
        w, h, zc = body_at(s)
        rings.append(arc_y(Y(s), w, h, zc, a0, a1, n=n, grow=1.01))
    return loft(rings, False, False, closed=False)

# the windscreen (under the raised visor in flight), and a row of small cabin windows on each side
make('Cockpit Windows', [strip(6.45, 7.35, 28, 152, n=10)], WINDOW, smooth=False)
cabin = []
for k in range(36):
    s = 11.6 + k * 0.9
    cabin += [strip(s, s + 0.32, 6, 11, n=3), strip(s, s + 0.32, 169, 174, n=3)]
make('Cabin Windows', cabin, WINDOW, smooth=False)

# ---------------- ogival delta wing: a long, gently curving leading edge, straight trailing edge, drooped tips ----------------
LE = [(1.2, 19.0), (1.45, 20.5), (2.2, 24.0), (3.4, 28.0), (5.2, 33.0), (7.0, 37.5), (9.2, 42.2), (11.4, 47.0),
      (12.3, 49.0), (12.6, 49.9), (12.8, 50.6)]
TE, HINGE_S = 51.6, 49.6  # trailing edge, and the elevon hinge line where elevons are fitted

def wz(x):
    return -1.05 - 0.0065 * x * x

def le_at(x):
    return interp(LE, x)[0]

def tc(x):
    return 0.03 - 0.005 * x / 12.8

def wing_piece(x0, x1, te, sx):
    n = max(1, round((x1 - x0) / 0.4))
    xs = [x0 + (x1 - x0) * k / n for k in range(n + 1)]
    return loft([span_section(x, Y(le_at(x)), te - le_at(x), wz(x), tc(x), sx) for x in xs])

# elevons: inner (between the fuselage and the nacelle), middle and outer; the wing behind the nacelle is fixed
ELEVONS = [('Inner', 1.55, 3.45), ('Middle', 6.32, 9.23), ('Outer', 9.27, 12.18)]
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Wing.' + side, [wing_piece(1.2, 1.55, TE, sx), wing_piece(1.55, 3.45, HINGE_S, sx), wing_piece(3.45, 6.32, TE, sx),
                          wing_piece(6.32, 12.18, HINGE_S, sx), wing_piece(12.18, 12.8, TE, sx)], WHITE)
    for name, x0, x1 in ELEVONS:
        xm = (x0 + x1) / 2
        make('Wing Elevon %s.%s' % (name, side),
             [loft([span_section(x, Y(HINGE_S), TE - HINGE_S, wz(x), 0.03, sx) for x in (x0, xm, x1)])], WHITE,
             origin=(sx * xm, Y(HINGE_S), wz(xm)))

# ---------------- fin: tall and swept, running down onto the tail cone ----------------
make('Vertical Tail', [loft([fin_section(z, Y(le), ch, 0.0, t) for z, le, ch, t in
     [(0.5, 52.0, 9.4, 0.035), (1.3, 47.0, 14.0, 0.035), (2.3, 50.3, 10.6, 0.035), (4.0, 55.2, 5.6, 0.035), (6.2, 58.9, 2.2, 0.03)]])], WHITE)

# ---------------- engines: two boxy nacelles under the wing, each with two Olympus 593s side by side ----------------
NAC_X, NAC_Z = 5.1, -2.35
ENG_DX = 0.6
for sx, side in ((1, 'L'), (-1, 'R')):
    x = sx * NAC_X
    make('Engine Nacelle.' + side, [loft([ring_y(Y(s), w, h, NAC_Z, x, n=24, p=5.0) for s, w, h in
         [(37.9, 1.16, 0.88), (38.6, 1.2, 0.93), (49.0, 1.2, 0.95), (51.8, 1.16, 0.9)]], False, False),
         box(x - 0.04, x + 0.04, Y(37.9), Y(39.5), NAC_Z - 0.9, NAC_Z + 0.9)], UNDER)
    make('Intake Face.' + side, [box(x + sgn * 0.08, x + sgn * 1.12, Y(38.7), Y(38.74), NAC_Z - 0.82, NAC_Z + 0.82) if sgn > 0 else
                                 box(x + sgn * 1.12, x + sgn * 0.08, Y(38.7), Y(38.74), NAC_Z - 0.82, NAC_Z + 0.82) for sgn in (1, -1)], INTAKE, smooth=False)
    for e in (-1, 1):
        ex = x + e * ENG_DX
        make('Exhaust Nozzle %s.%s' % ('a' if e < 0 else 'b', side),
             [loft([ring_y(Y(s), r, r, NAC_Z, ex, n=20) for s, r in [(51.6, 0.55), (52.6, 0.56), (53.4, 0.5)]], False, False)], METAL)
        make('Exhaust Inner %s.%s' % ('a' if e < 0 else 'b', side), [loft([ring_y(Y(s), 0.47, 0.47, NAC_Z, ex, n=20) for s in (52.7, 52.8)])], SOOT)

# ---------------- landing gear: four-wheel main bogies, twin nose wheels, a small tail bumper ----------------
R_MAIN, W_MAIN, R_NOSE = 0.6, 0.32, 0.4
MAIN_X, MAIN_Y = 3.86, Y(39.4)
for sx, side in ((1, 'L'), (-1, 'R')):
    x = sx * MAIN_X
    make('Main Gear Strut.' + side, [cyl_z(x, MAIN_Y, -GEAR + R_MAIN, -1.45, 0.16),
                                     cyl_y(x, -GEAR + R_MAIN, MAIN_Y - 0.8, MAIN_Y + 0.8, 0.1)], STRUT)
    for i, (dx, dy) in enumerate([(-0.36, -0.62), (0.36, -0.62), (-0.36, 0.62), (0.36, 0.62)]):
        make('Main Wheel %s.%s' % ('abcd'[i], side), [wheel(x + dx, MAIN_Y + dy, -GEAR + R_MAIN, R_MAIN, W_MAIN)], TIRE)
NOSE_Y = Y(20.0)
make('Nose Gear Strut', [cyl_z(0, NOSE_Y, -GEAR + R_NOSE, -1.5, 0.12), box(-0.3, 0.3, NOSE_Y - 0.05, NOSE_Y + 0.05, -GEAR + R_NOSE - 0.05, -GEAR + R_NOSE + 0.05)], STRUT)
make('Nose Wheel a', [wheel(0.25, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.24)], TIRE)
make('Nose Wheel b', [wheel(-0.25, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.24)], TIRE)
TAIL_Y = Y(55.0)
make('Tail Bumper Strut', [cyl_z(0, TAIL_Y, -2.0, -0.5, 0.07)], STRUT)
make('Tail Bumper Wheel', [wheel(0.1, TAIL_Y, -2.0, 0.18, 0.1), wheel(-0.1, TAIL_Y, -2.0, 0.18, 0.1)], TIRE)


# ---------------- export ----------------
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='SELECT')
# this exporter only writes .gltf + .bin, so write those to a temp folder and fold the buffer into one JSON file
tmp = tempfile.mkdtemp()
bpy.ops.export_scene.gltf(filepath=os.path.join(tmp, 'concorde.gltf'), export_format='GLTF_SEPARATE', use_selection=False,
                          export_yup=True, export_apply=True, export_texcoords=False, export_animations=False,
                          export_cameras=False, export_lights=False)
with open(os.path.join(tmp, 'concorde.gltf')) as f:
    gltf = json.load(f)
for b in gltf['buffers']:
    with open(os.path.join(tmp, b['uri']), 'rb') as f:
        b['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(f.read()).decode()
with open(OUT, 'w') as f:
    json.dump(gltf, f, separators=(',', ':'))
shutil.rmtree(tmp)

# numbers the sim needs, in sim coordinates (x right, y up, z aft)
sim = lambda p: [round(-p[0], 2), round(p[2], 2), round(p[1], 2)]
print('NOZZLES', [sim((sx * NAC_X + e * ENG_DX, Y(53.4), NAC_Z)) for sx in (1, -1) for e in (-1, 1)])
print('HINGE', sim(HINGE), 'TIP', sim((12.8, Y(51.1), wz(12.8))), 'FIN_TOP 6.2', 'TAIL', sim((0, Y(61.66), 0.4)))
lo = [min(v[i] for o in scene.objects if o.type == 'MESH' for v in [o.matrix_world @ p.co for p in o.data.vertices]) for i in range(3)]
hi = [max(v[i] for o in scene.objects if o.type == 'MESH' for v in [o.matrix_world @ p.co for p in o.data.vertices]) for i in range(3)]
print('BOUNDS blender', [round(v, 2) for v in lo], [round(v, 2) for v in hi])
print('MESHES %d  TRIS %d' % (sum(o.type == 'MESH' for o in scene.objects),
                              sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')))
