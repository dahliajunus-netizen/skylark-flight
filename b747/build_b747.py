# Boeing 747-8 for Skylark: 76.25 m long, 68.4 m span, 19.35 m tall (Boeing airport planning dimensions).
# Run headless:  blender --background --python b747/build_b747.py -- B747.gltf.json
#
# Blender axes: nose toward -Y, up +Z, the pilot's left wing on +X. The glTF export turns this into
# nose +Z, and the sim turns it again to nose -Z, so a point (bx, by, bz) here is (-bx, bz, by) in the sim.
# The origin is the centre of gravity, just ahead of the main gear; the wheels touch the ground at z = -GEAR.
# Part names follow the sim's rules: wheels, struts and bogie beams are the gear, "Stabilizer" pivots for pitch,
# "Speed Brake Spoiler" hinges up, Wing/Fin/Stabilizer are damage zones, Nacelle/Fan Face/Exhaust Cone/Engine
# Pylon are the four engine pods. The livery matches the sim's 757.
import bpy, bmesh, math, sys, json, os, base64, shutil, tempfile

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'B747.gltf.json'
GEAR = 5.5

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root = bpy.data.objects.new('Boeing 747-8', None)
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

# same paint as the 757
WHITE = material('Fuselage White', '#f2f2ee', 0.1, 0.45)
BELLY = material('Belly Grey', '#c8cdd1', 0.15, 0.5)
BLUE = material('Livery Blue', '#204d8c', 0.1, 0.5)
WINGM = material('Wing Grey', '#c3c8cd', 0.3, 0.5)
NAC = material('Nacelle', '#d5d8db', 0.4, 0.4)
WIN = material('Windows', '#1d2731', 0.5, 0.2)
INTAKE = material('Intake Dark', '#0e1012', 0.0, 0.8)
METAL = material('Nozzle Metal', '#4a4642', 0.85, 0.35)
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


# ---------------- fuselage ----------------
NOSE_Y, TAIL_Y = -33.5, 42.75
# station y, half-width, half-height, centre z (main deck: a 6.5 m tube)
FUS = [(NOSE_Y, 0.08, 0.08, -0.7), (-33.1, 1.2, 1.15, -0.5), (-32.2, 2.15, 2.1, -0.28), (-30.8, 2.8, 2.78, -0.1),
       (-28.8, 3.18, 3.15, 0.0), (-26.0, 3.25, 3.25, 0.0), (16.0, 3.25, 3.25, 0.0), (20.0, 3.1, 3.08, 0.18),
       (25.0, 2.7, 2.6, 0.6), (30.0, 2.1, 1.95, 1.1), (35.0, 1.42, 1.25, 1.6), (39.0, 0.75, 0.6, 2.0),
       (TAIL_Y - 0.4, 0.3, 0.25, 2.25), (TAIL_Y, 0.06, 0.06, 2.3)]
fus_at = lambda y: interp(FUS, y)
make('Fuselage', [loft([ring_y(y, w, h, zc, n=32) for y, w, h, zc in FUS])], WHITE)
# the hump: the upper deck runs from the cockpit back past the wing leading edge
UPPER = [(-32.7, 0.35, 0.28, 1.35), (-31.8, 1.45, 1.15, 2.05), (-30.3, 2.15, 1.62, 2.72), (-27.5, 2.45, 1.78, 3.05),
         (-12.0, 2.45, 1.78, 3.05), (-8.0, 2.3, 1.5, 2.92), (-4.5, 1.65, 0.95, 2.78), (-1.5, 0.45, 0.28, 2.85)]
upper_at = lambda y: interp(UPPER, y)
make('Upper Deck', [loft([ring_y(y, w, h, zc, n=28) for y, w, h, zc in UPPER])], WHITE)

# livery: grey belly, blue cheatline under the windows, window bands on both decks, cockpit glazing
bands = lambda a0, a1, y0, y1, table, n=4, steps=24: loft(
    [arc_y(y, *interp(table, y), a0, a1, n) for y in (y0 + (y1 - y0) * k / steps for k in range(steps + 1))], False, False, closed=False)
make('Belly', [bands(200, 340, -31.5, 38.0, FUS, n=24)], BELLY)
make('Cheatline', [bands(-3, 5, -31.0, 37.0, FUS), bands(175, 183, -31.0, 37.0, FUS)], BLUE)
make('Cabin Windows', [bands(12, 17, -28.0, 24.0, FUS, 3), bands(163, 168, -28.0, 24.0, FUS, 3),
                       bands(18, 26, -26.0, -9.5, UPPER, 3), bands(154, 162, -26.0, -9.5, UPPER, 3)], WIN)
make('Windscreen', [bands(32, 148, -31.65, -30.85, UPPER, 9, 4)], WIN)
# wing-to-body fairing under the centre section
make('Wing Body Fairing', [loft([ring_y(y, w, h, zc, n=24) for y, w, h, zc in
     [(-12.0, 2.4, 0.4, -2.75), (-9.0, 3.3, 1.2, -2.35), (0.0, 3.55, 1.45, -2.2), (8.0, 3.45, 1.35, -2.25), (12.0, 2.6, 0.5, -2.7)]])], BELLY)


# ---------------- wings ----------------
DIH = math.tan(math.radians(7))
ROOT_X, ROOT_Z = 1.0, -2.3
def wz(x):
    return ROOT_Z + (x - ROOT_X) * DIH
# span x, leading edge y, chord, thickness/chord (LE swept ~40°, raked tip)
WING = [(ROOT_X, -8.0, 15.5, 0.13), (12.5, 1.65, 8.5, 0.105), (33.0, 18.85, 3.6, 0.085), (34.2, 21.0, 1.7, 0.06)]
def wing_at(x):
    w = interp([(s[0], s[1], s[2], s[3]) for s in WING], x)
    return w[0], w[1], wz(x), w[2]   # le, chord, z, t

SPOILERS = [(14.0, 19.5), (20.0, 25.5)]
FAIRINGS = [7.5, 15.0, 19.5, 25.0]
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Wing.' + side, [loft([span_section(x, le, c, wz(x), t, sx) for x, le, c, t in WING])], WINGM)
    # spoilers on top of the outer wing, ahead of the flaps; they hinge up for the speed brake
    for i, (x0, x1) in enumerate(SPOILERS):
        pts = []
        for x in (x0, x1):
            le, c, z, t = wing_at(x)
            top = z + 0.5 * t * c * 0.72
            pts.append((sx * x, le + 0.62 * c, top, le + 0.74 * c))
        (ax, ay0, az, ay1), (bx, by0, bz, by1) = pts
        v = [(ax, ay0, az), (ax, ay1, az - 0.05), (bx, by1, bz - 0.05), (bx, by0, bz),
             (ax, ay0, az + 0.06), (ax, ay1, az + 0.01), (bx, by1, bz + 0.01), (bx, by0, bz + 0.06)]
        f = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        make('Speed Brake Spoiler %d.%s' % (i + 1, side), [(v, f)], WINGM, smooth=False)
    # flap-track canoes under the trailing edge
    for i, x in enumerate(FAIRINGS):
        le, c, z, t = wing_at(x)
        y0, y1, zc = le + 0.55 * c, le + c + 1.6, z - 0.5 * t * c * 0.6
        make('Flap Fairing %d.%s' % (i + 1, side), [loft([ring_y(y, w, h, zc - h * 0.6, sx * x, n=12) for y, w, h in
             [(y0, 0.05, 0.05), (y0 + 1.0, 0.26, 0.42), (y1 - 1.6, 0.26, 0.5), (y1, 0.05, 0.08)]])], WINGM)

# ---------------- tail ----------------
STAB_Z = 1.65
for sx, side in ((1, 'L'), (-1, 'R')):
    st = [(1.0, 30.2, 9.2, STAB_Z, 0.1), (11.0, 38.6, 3.2, STAB_Z + 10.0 * DIH, 0.08)]
    make('Stabilizer.' + side, [loft([span_section(x, le, c, z, t, sx) for x, le, c, z, t in st])], WHITE,
         origin=(sx * 1.0, 34.6, STAB_Z))
FIN_TOP = 19.35 - GEAR
make('Fin', [loft([fin_section(z, le, c, 0.0, t) for z, le, c, t in
     [(1.6, 25.6, 13.6, 0.11), (3.2, 27.3, 11.9, 0.11), (FIN_TOP - 0.3, 36.4, 4.6, 0.09), (FIN_TOP, 36.9, 3.9, 0.07)]])], BLUE)

# ---------------- engines: four GEnx-2B ----------------
ENGINES = [(11.84, 1), (21.03, 2)]
for sx, side in ((1, 'L'), (-1, 'R')):
    for ex, k in ENGINES:
        le, c, z, t = wing_at(ex)
        ez = z - 0.5 * t * c - (1.6 if k == 1 else 1.75)   # nacelle centre, hung below and ahead of the wing
        y0 = le - 4.6                                       # intake lip
        x = sx * ex
        make('Nacelle %d.%s' % (k, side), [loft([ring_y(y, r, r, ez, x, n=32) for y, r in
             [(y0 + 0.55, 1.22), (y0 + 0.08, 1.3), (y0, 1.4), (y0 + 0.12, 1.5), (y0 + 1.1, 1.56), (y0 + 2.8, 1.52),
              (y0 + 4.6, 1.3), (y0 + 5.4, 1.08), (y0 + 5.3, 1.0)]], False, False)], NAC)
        make('Fan Face %d.%s' % (k, side), [loft([ring_y(y, r, r, ez, x, n=32) for y, r in [(y0 + 0.5, 1.23), (y0 + 0.55, 1.23)]]),
                                           loft([ring_y(y, r, r, ez, x, n=14) for y, r in [(y0 + 0.2, 0.03), (y0 + 0.5, 0.42)]])], INTAKE)
        make('Exhaust Cone %d.%s' % (k, side), [loft([ring_y(y, r, r, ez, x, n=20) for y, r in [(y0 + 5.25, 1.02), (y0 + 5.3, 1.02)]]),
                                               loft([ring_y(y, r, r, ez, x, n=20) for y, r in [(y0 + 5.3, 0.62), (y0 + 6.9, 0.08)]])], METAL)
        # pylon from the top of the nacelle up into the wing's underside
        under = z - 0.5 * t * c * 0.8
        pv = [(x - 0.32, y0 + 1.6, ez + 1.2), (x + 0.32, y0 + 1.6, ez + 1.2), (x + 0.32, le + 0.55 * c, ez + 1.1), (x - 0.32, le + 0.55 * c, ez + 1.1),
              (x - 0.32, y0 + 2.6, under + 0.3), (x + 0.32, y0 + 2.6, under + 0.3), (x + 0.32, le + 0.6 * c, under + 0.3), (x - 0.32, le + 0.6 * c, under + 0.3)]
        make('Engine Pylon %d.%s' % (k, side), [(pv, [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])], NAC, smooth=False)

# ---------------- landing gear: nose, two wing gear and two body gear, 18 wheels ----------------
R_MAIN, W_MAIN, R_NOSE = 0.63, 0.46, 0.6
def truck(name, sx, x, y, top):
    """four-wheel bogie on a strut: wheels 1.1 m apart across, 1.45 m fore and aft."""
    zc = -GEAR + R_MAIN
    make('Main Gear Strut %s.%s' % (name, 'L' if sx > 0 else 'R'), [cyl_z(sx * x, y, zc + 0.15, top, 0.2)], STRUT)
    make('Main Gear Bogie Beam %s.%s' % (name, 'L' if sx > 0 else 'R'), [cyl_y(sx * x, zc, y - 0.95, y + 0.95, 0.13)], STRUT)
    for i, (dx, dy) in enumerate([(-0.55, -0.72), (0.55, -0.72), (-0.55, 0.72), (0.55, 0.72)]):
        make('Main Wheel %s%s.%s' % (name, 'abcd'[i], 'L' if sx > 0 else 'R'), [wheel(sx * x + dx, y + dy, zc, R_MAIN, W_MAIN)], TIRE)
for sx in (1, -1):
    le, c, z, t = wing_at(5.5)
    truck('Wing', sx, 5.5, 1.55, z - 0.5 * t * c * 0.7)
    truck('Body', sx, 1.92, 4.55, -2.6)
nose_y = -26.5
make('Nose Gear Strut', [cyl_z(0, nose_y, -GEAR + R_NOSE, -2.9, 0.17), cyl_y(0, -GEAR + R_NOSE, nose_y - 0.05, nose_y + 0.05, 0.12)], STRUT)
make('Nose Wheel a', [wheel(0.42, nose_y, -GEAR + R_NOSE, R_NOSE, 0.42)], TIRE)
make('Nose Wheel b', [wheel(-0.42, nose_y, -GEAR + R_NOSE, R_NOSE, 0.42)], TIRE)


# ---------------- export ----------------
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='SELECT')
# this exporter only writes .gltf + .bin, so write those to a temp folder and fold the buffer into one JSON file
tmp = tempfile.mkdtemp()
bpy.ops.export_scene.gltf(filepath=os.path.join(tmp, 'b747.gltf'), export_format='GLTF_SEPARATE', use_selection=False,
                          export_yup=True, export_apply=True, export_texcoords=False, export_animations=False,
                          export_cameras=False, export_lights=False)
with open(os.path.join(tmp, 'b747.gltf')) as f:
    gltf = json.load(f)
for b in gltf['buffers']:
    with open(os.path.join(tmp, b['uri']), 'rb') as f:
        b['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(f.read()).decode()
with open(OUT, 'w') as f:
    json.dump(gltf, f, separators=(',', ':'))
shutil.rmtree(tmp)

# numbers the sim needs, in sim coordinates (x right, y up, z aft)
sim = lambda p: [round(-p[0], 2), round(p[2], 2), round(p[1], 2)]
for sx, side in ((1, 'L'), (-1, 'R')):
    for ex, k in ENGINES:
        le, c, z, t = wing_at(ex)
        print('ENGINE %d%s intake %s bottom %.2f' % (k, side, sim((sx * ex, le - 4.6, 0)), z - 0.5 * t * c - (1.6 if k == 1 else 1.75) - 1.56))
print('FIN_TOP %.2f  TIP %s' % (FIN_TOP, sim((34.2, 21.0, wz(34.2)))))
print('MESHES %d  TRIS %d' % (sum(o.type == 'MESH' for o in scene.objects),
                              sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')))
