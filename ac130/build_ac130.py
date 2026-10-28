# Lockheed Martin AC-130J Ghostrider for Skylark: 29.79 m long, 40.41 m span, 11.84 m tall (USAF C-130J figures),
# four AE 2100D3 turboprops with six-blade Dowty R391 propellers, 4.11 m across.
# Run headless:  blender --background --python ac130/build_ac130.py -- AC130.gltf.json
#
# Blender axes: nose toward -Y, up +Z, the pilot's left wing on +X. The glTF export turns this into
# nose +Z, and the sim turns it again to nose -Z, so a point (bx, by, bz) here is (-bx, bz, by) in the sim.
# The origin is the centre of gravity; the wheels touch the ground at z = -GEAR.
# Part names follow the sim's rules: wheels and struts are the gear, "Stabilizer" pivots for pitch, Wing/Fin/
# Stabilizer are damage zones, and each "Nacelle" (with its propeller) is an engine. Propellers are separate
# objects with their origin on the hub so the sim can spin them. The guns stick out of the left (port) side.
import bpy, bmesh, math, sys, json, os, base64, shutil, tempfile

OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else 'AC130.gltf.json'
GEAR = 3.2

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
root = bpy.data.objects.new('AC-130J', None)
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

GREY = material('Gunship Grey', '#585e63', 0.15, 0.6)
GREY_D = material('Gunship Grey Dark', '#43484c', 0.15, 0.6)
RADOME = material('Radome', '#3a3f43', 0.0, 0.5)
WIN = material('Windows', '#141b22', 0.5, 0.15)
PROP = material('Propeller', '#25282b', 0.2, 0.5)
SPIN = material('Spinner', '#4a4f53', 0.4, 0.4)
GUN = material('Gun Metal', '#2a2c2e', 0.8, 0.35)
GLASS = material('Sensor Glass', '#1b2430', 0.7, 0.1)
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



def ring_tb(y, w, top, bot, xc=0.0, n=28, p=2.6):
    """superellipse section given by its top and bottom heights (the C-130's boxy hold)."""
    return ring_y(y, w, (top - bot) / 2, (top + bot) / 2, xc, n, p)


# ---------------- fuselage ----------------
# station y, half-width, top, bottom: a 4.3 m wide box-ish hold, the nose with its radome, and the upswept
# tail over the rear ramp
FUS = [(-13.9, 0.1, -0.2, -0.5), (-13.5, 1.0, 0.75, -1.25), (-12.8, 1.65, 1.5, -1.8), (-11.8, 2.0, 2.05, -2.1),
       (-10.5, 2.15, 2.3, -2.3), (5.0, 2.15, 2.3, -2.3), (7.5, 2.05, 2.3, -1.6), (10.0, 1.8, 2.25, -0.4),
       (12.5, 1.3, 2.1, 0.6), (14.5, 0.8, 1.95, 1.2), (15.9, 0.15, 1.75, 1.5)]
make('Fuselage', [loft([ring_tb(y, w, t, b) for y, w, t, b in FUS[3:]])], GREY)
# the radar nose, darker, blending into the fuselage
make('Radome', [loft([ring_tb(y, w, t, b) for y, w, t, b in FUS[:4]], True, False)], RADOME)
# cockpit glazing: a band of windows across the top of the nose
arc = lambda y, w, t, b, a0, a1, n=12, g=1.01: [(w * g * math.cos(a), y, (t + b) / 2 + (t - b) / 2 * g * math.sin(a))
                                                 for a in (math.radians(a0 + (a1 - a0) * k / (n - 1)) for k in range(n))]
make('Windscreen', [loft([arc(y, *interp(FUS, y), 28, 152) for y in (-12.55, -12.25, -11.95)], False, False, closed=False)], WIN)
# main gear sponsons along the lower sides, and the wing-root fairing on top
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Sponson.' + side, [loft([ring_y(y, w, h, -1.45, sx * 2.05, n=20) for y, w, h in
         [(-3.6, 0.05, 0.3), (-2.8, 0.5, 0.85), (2.6, 0.5, 0.85), (3.8, 0.05, 0.3)]])], GREY)
make('Centre Fairing', [loft([ring_y(y, w, h, 2.25, n=20) for y, w, h in
     [(-3.4, 0.3, 0.1), (-2.2, 1.6, 0.45), (3.4, 1.6, 0.45), (5.4, 0.3, 0.1)]])], GREY)


# ---------------- wings ----------------
# high, straight wing: 4.9 m root chord tapering to 2.6 m, a little dihedral outboard of the inner engines
WZ, DIH = 2.05, math.tan(math.radians(2.5))
def wz(x):
    return WZ + max(0.0, x - 5.0) * DIH
WING = [(0.0, -2.0, 4.9, 0.18), (5.0, -1.85, 4.55, 0.17), (20.2, -1.15, 2.6, 0.12)]
def wing_at(x):
    le, c, t = interp([(s[0], s[1], s[2], s[3]) for s in WING], x)
    return le, c, wz(x), t
ENGINES = [(4.9, 1), (10.0, 2)]
for sx, side in ((1, 'L'), (-1, 'R')):
    make('Wing.' + side, [loft([span_section(x, le, c, wz(x), t, sx) for x, le, c, t in WING] +
                               [span_section(20.4, -0.95, 2.2, wz(20.4), 0.06, sx)])], GREY)
    # external fuel tank on a pylon between the engines
    le, c, z, t = wing_at(7.45)
    tz = z - 0.5 * t * c - 0.95
    make('Wing Tank.' + side, [loft([ring_y(y, r, r, tz, sx * 7.45, n=18) for y, r in
         [(le - 2.6, 0.05), (le - 2.0, 0.42), (le - 0.8, 0.6), (le + 3.0, 0.6), (le + 4.6, 0.3), (le + 5.2, 0.05)]])], GREY)
    make('Wing Pylon Tank.' + side, [box(sx * 7.45 - 0.08, sx * 7.45 + 0.08, le + 0.2, le + 2.6, tz + 0.5, z - 0.3)], GREY_D, smooth=False)

    # ---------------- engines and propellers ----------------
    for ex, k in ENGINES:
        le, c, z, t = wing_at(ex)
        x, ez = sx * ex, z - 0.55            # nacelle centre, under the wing
        y0 = le - 3.4                         # front of the nacelle, just behind the propeller
        make('Nacelle %d.%s' % (k, side), [loft([ring_y(y, w, h, ez - d, x, n=22, p=2.3) for y, w, h, d in
             [(y0, 0.42, 0.42, 0.0), (y0 + 0.5, 0.62, 0.78, 0.18), (y0 + 2.0, 0.72, 0.95, 0.25), (le + 1.0, 0.72, 0.95, 0.2),
              (le + c * 0.95, 0.55, 0.7, 0.1), (le + c + 1.2, 0.12, 0.15, -0.1)]])], GREY)
        make('Exhaust Stub %d.%s' % (k, side), [cyl_z(x + sx * 0.55, le + 0.3, ez + 0.3, ez + 0.85, 0.16)], METAL)
        # spinner and the six-blade propeller, built around its hub so it can turn
        hub = (x, y0 - 0.45, ez)
        make('Spinner %d.%s' % (k, side), [loft([ring_y(y, r, r, ez, x, n=16) for y, r in
             [(y0 - 1.25, 0.02), (y0 - 1.0, 0.25), (y0 - 0.55, 0.42), (y0 + 0.05, 0.42)]])], SPIN)
        blades = []
        for i in range(6):
            a = 2 * math.pi * i / 6 + 0.26
            ca, sa = math.cos(a), math.sin(a)
            rings = []
            for rr, chord, thick, twist in [(0.35, 0.34, 0.09, 0.9), (1.0, 0.36, 0.06, 0.55), (1.7, 0.27, 0.04, 0.3), (2.055, 0.12, 0.02, 0.2)]:
                # a flat section across the blade, twisted to its pitch angle, swept back a little at the tip (scimitar)
                sweep = 0.18 * (rr / 2.055) ** 2
                sec = []
                for u, v in [(-chord / 2, 0), (0, thick / 2), (chord / 2, 0), (0, -thick / 2)]:
                    tang = u * math.cos(twist) + sweep     # along the circle
                    axial = u * math.sin(twist) + v        # along the shaft
                    px = rr * ca - tang * sa
                    pz = rr * sa + tang * ca
                    sec.append((hub[0] + px, hub[1] + axial, hub[2] + pz))
                rings.append(sec)
            blades.append(loft(rings))
        make('Nacelle Propeller %d.%s' % (k, side), blades, PROP, origin=hub)


# ---------------- tail ----------------
STAB_Z = 1.95
for sx, side in ((1, 'L'), (-1, 'R')):
    st = [(0.5, 11.6, 4.0, STAB_Z, 0.11), (8.0, 12.9, 2.1, STAB_Z, 0.09)]
    make('Stabilizer.' + side, [loft([span_section(x, le, c, z, t, sx) for x, le, c, z, t in st])], GREY,
         origin=(sx * 0.5, 13.3, STAB_Z))
FIN_TOP = 11.84 - GEAR
make('Fin', [loft([fin_section(z, le, c, 0.0, t) for z, le, c, t in
     [(1.6, 8.6, 7.2, 0.12), (2.6, 9.4, 6.4, 0.12), (FIN_TOP - 0.4, 12.9, 2.9, 0.1), (FIN_TOP, 13.3, 2.2, 0.07)]])], GREY)


# ---------------- gunship: sensors and guns on the left side ----------------
# electro-optical / infrared sensor turrets: under the nose (port) and behind the left main gear
for name, (x, y, z, r) in {'Sensor Turret Nose': (1.15, -10.9, -2.15, 0.42), 'Sensor Turret Aft': (1.7, 4.6, -2.15, 0.36)}.items():
    make(name, [loft([ring_y(y + r * math.cos(a), r * math.sin(a) + 0.01, r * math.sin(a) + 0.01, z, x, n=16)
                      for a in [math.pi * k / 10 for k in range(11)]])], GREY_D)
    make(name + ' Window', [loft([ring_y(y - r * 0.96 + d, rr, rr, z - 0.06, x + 0.05, n=12) for d, rr in [(0.0, 0.2), (0.02, 0.2)]])], GLASS)
GUN30 = (2.95, -6.6, -0.95)   # muzzle of the 30 mm GAU-23/A, just forward of the wing
GUN105 = (3.75, 4.1, -1.3)    # muzzle of the 105 mm M102, aft of the wing
make('GAU-23 Mount', [loft([ring_y(y, w, h, -0.95, 2.1, n=16) for y, w, h in [(-7.3, 0.05, 0.2), (-7.0, 0.42, 0.45), (-6.2, 0.42, 0.45), (-5.9, 0.05, 0.2)]])], GREY_D)
make('GAU-23 Barrel', [loft([[(x, -6.6 + 0.07 * math.cos(a), -0.95 + 0.07 * math.sin(a)) for a in (2 * math.pi * k / 10 for k in range(10))] for x in (2.3, GUN30[0])])], GUN)
make('M102 Mount', [loft([ring_y(y, w, h, -1.3, 2.1, n=16) for y, w, h in [(3.2, 0.05, 0.3), (3.5, 0.55, 0.62), (4.8, 0.55, 0.62), (5.1, 0.05, 0.3)]])], GREY_D)
make('M102 Barrel', [loft([[(x, 4.1 + r * math.cos(a), -1.3 + r * math.sin(a)) for a in (2 * math.pi * k / 12 for k in range(12))] for x, r in
     [(2.4, 0.16), (3.45, 0.11), (3.5, 0.17), (GUN105[0], 0.17)]])], GUN)


# ---------------- landing gear: two tandem pairs in the sponsons, twin nose wheels ----------------
R_MAIN, W_MAIN, R_NOSE = 0.71, 0.5, 0.48
for sx, side in ((1, 'L'), (-1, 'R')):
    for i, dy in enumerate((-0.95, 0.95)):
        make('Main Wheel %d.%s' % (i + 1, side), [wheel(sx * 2.2, dy, -GEAR + R_MAIN, R_MAIN, W_MAIN)], TIRE)
        make('Main Gear Strut %d.%s' % (i + 1, side), [cyl_z(sx * 1.85, dy, -GEAR + R_MAIN, -1.2, 0.11),
                                                        cyl_y(sx * 1.85, -GEAR + R_MAIN, dy - 0.05, dy + 0.05, 0.08)], STRUT)
NOSE_Y = -10.7
make('Nose Gear Strut', [cyl_z(0, NOSE_Y, -GEAR + R_NOSE, -2.0, 0.12), cyl_y(0, -GEAR + R_NOSE, NOSE_Y - 0.05, NOSE_Y + 0.05, 0.09)], STRUT)
make('Nose Wheel a', [wheel(0.33, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.3)], TIRE)
make('Nose Wheel b', [wheel(-0.33, NOSE_Y, -GEAR + R_NOSE, R_NOSE, 0.3)], TIRE)


# ---------------- export ----------------
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='SELECT')
# this exporter only writes .gltf + .bin, so write those to a temp folder and fold the buffer into one JSON file
tmp = tempfile.mkdtemp()
bpy.ops.export_scene.gltf(filepath=os.path.join(tmp, 'ac130.gltf'), export_format='GLTF_SEPARATE', use_selection=False,
                          export_yup=True, export_apply=True, export_texcoords=False, export_animations=False,
                          export_cameras=False, export_lights=False)
with open(os.path.join(tmp, 'ac130.gltf')) as f:
    gltf = json.load(f)
for b in gltf['buffers']:
    with open(os.path.join(tmp, b['uri']), 'rb') as f:
        b['uri'] = 'data:application/octet-stream;base64,' + base64.b64encode(f.read()).decode()
with open(OUT, 'w') as f:
    json.dump(gltf, f, separators=(',', ':'))
shutil.rmtree(tmp)

# numbers the sim needs, in sim coordinates (x right, y up, z aft)
sim = lambda p: [round(-p[0], 2), round(p[2], 2), round(p[1], 2)]
print('GUN30', sim(GUN30), 'GUN105', sim(GUN105), 'SENSOR', sim((1.15, -10.9, -2.15)), 'FIN_TOP %.2f' % FIN_TOP)
for sx in (1, -1):
    for ex, k in ENGINES:
        le, c, z, t = wing_at(ex)
        print('PROP %d' % k, sim((sx * ex, le - 3.85, z - 0.55)))
print('MESHES %d  TRIS %d' % (sum(o.type == 'MESH' for o in scene.objects),
                              sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in scene.objects if o.type == 'MESH')))
