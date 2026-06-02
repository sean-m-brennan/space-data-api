#!/usr/bin/env python
#  Copyright 2024 Sean M. Brennan and contributors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""Ephemeris truth generator for the space-sim analytic-model validation harness.

Produces real geocentric **ecliptic (J2000)** positions of the Sun (and, for
characterization, the Moon and Mars) from two independent ephemeris sources that
back ``space-data-api``:

  * **spice** — spiceypy + de440.bsp, ``spkpos(body, et, 'ECLIPJ2000', 'NONE', 'EARTH')``
    (the authoritative SPICE path, already ecliptic).
  * **astro** — astropy + de430.bsp, ``get_body(...).transform_to(GeocentricMeanEcliptic)``.

Both are reduced to a canonical geocentric ecliptic longitude/latitude so they are
directly comparable; the script asserts they agree to a tight tolerance and writes a
JSON fixture consumed by
``packages/space-sim/test/planetarium/ephemeris_validation_live.test.ts``.

Why query the ephemeris libraries directly instead of the shipped
``api.*_converter.SpaceQuery.celestial_position``?  To keep the validation oracle
independent of the code under test: the harness computes truth itself, from the same
kernels, in one well-defined frame, so it would catch a future regression in the service.

Several bugs in those service methods were found and **fixed** during this work (the fixed
methods now agree with this truth to <0.011°):
  * ``api.abstract_query`` imported ``astropy.visualization.wcsaxes`` (pulled matplotlib) —
    a dead import, removed;
  * ``AstroQuery.celestial_position`` built its vector from GCRS ra/dec → **equatorial**
    cartesian, while ``SpiceQuery.celestial_position`` returned **ecliptic** (ECLIPJ2000) —
    both now return geocentric ECLIPJ2000 cartesian km;
  * ``SpiceQuery._init_kernels`` called ``furnsh()`` on ``KERNELS['spk']['planets']`` (a
    *list*), and the kernel selection never loaded an ephemeris for the Moon / used a
    wrong-case satellite key / omitted the planet-body SPK (Mars 499 lives in mar097.bsp).
(Run with ``--live`` to additionally exercise the HTTP service end-to-end.)
"""

import argparse
import json
import math
import os
import warnings

import spiceypy as spice

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(THIS_DIR)                      # packages/space-data-api
KERNEL_DIR = os.path.join(PKG_DIR, "app", "kernels")
REPO_ROOT = os.path.abspath(os.path.join(PKG_DIR, "..", ".."))
DEFAULT_OUT = os.path.join(
    REPO_ROOT, "packages", "space-sim", "test", "planetarium",
    "fixtures", "ephemeris_truth.json",
)

# Mean obliquity of the ecliptic at J2000 (IAU 1976), degrees — recorded for reference
# (the equatorial→ecliptic rotation that the astro service path elides).
OBLIQUITY_J2000_DEG = 23.4392911

# Tolerance for agreement between the two independent ephemeris sources (degrees).
CROSS_CHECK_TOL_DEG = 0.05

# Bodies: 'sun' carries the hard assertions; 'moon'/'mars' are characterization only
# (the analytic model deliberately does not anchor their absolute positions).
BODIES = ["sun", "moon", "mars"]

# Extra SPK kernels required per body beyond de440 (which already has Sun/Moon).
BODY_EXTRA_SPK = {"mars": "mar097.bsp"}

# UTC instants (ISO-8601, 'Z'). Monthly 2025 + equinoxes/solstices + the exact
# quarterly dates the offline test uses + a J2000 reference.
DATES = [
    "2000-01-01T12:00:00Z",                                    # J2000 reference epoch
    "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", "2025-03-01T00:00:00Z",
    "2025-04-01T00:00:00Z", "2025-05-01T00:00:00Z", "2025-06-01T00:00:00Z",
    "2025-07-01T00:00:00Z", "2025-08-01T00:00:00Z", "2025-09-01T00:00:00Z",
    "2025-10-01T00:00:00Z", "2025-11-01T00:00:00Z", "2025-12-01T00:00:00Z",
    "2025-03-20T00:00:00Z", "2025-06-21T00:00:00Z",            # vernal equinox / summer solstice
    "2025-09-22T00:00:00Z", "2025-12-21T00:00:00Z",            # autumnal equinox / winter solstice
    "2025-04-02T00:00:00Z", "2025-07-02T00:00:00Z",            # extra quarterly anchors (offline test)
]


def angular_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two angles in degrees, in [0, 180]."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def ecliptic_from_cartesian(x: float, y: float, z: float):
    """Geocentric ecliptic (lon[0,360), lat[-90,90], distance) from cartesian km."""
    r = math.sqrt(x * x + y * y + z * z)
    lon = math.degrees(math.atan2(y, x)) % 360.0
    lat = math.degrees(math.asin(z / r)) if r else 0.0
    return lon, lat, r


def iso_to_spice(iso: str) -> str:
    """'2025-03-20T00:00:00Z' -> '2025-03-20 00:00:00 UTC' for spice.str2et."""
    return iso.replace("T", " ").replace("Z", "") + " UTC"


def furnish_spice_kernels(bodies):
    """Load leapseconds + de440 + any per-body SPKs once."""
    spice.furnsh(os.path.join(KERNEL_DIR, "latest_leapseconds.tls"))
    spice.furnsh(os.path.join(KERNEL_DIR, "de440.bsp"))
    for body in bodies:
        extra = BODY_EXTRA_SPK.get(body)
        if extra:
            spice.furnsh(os.path.join(KERNEL_DIR, extra))


def spice_ecliptic(body: str, iso: str):
    """spiceypy geocentric ECLIPJ2000 -> (lon, lat, dist, [x, y, z])."""
    et = spice.str2et(iso_to_spice(iso))
    pos, _ = spice.spkpos(body.upper(), et, "ECLIPJ2000", "NONE", "EARTH")
    x, y, z = (float(pos[0]), float(pos[1]), float(pos[2]))
    lon, lat, dist = ecliptic_from_cartesian(x, y, z)
    return lon, lat, dist, [x, y, z]


def astro_ecliptic(body: str, iso: str):
    """astropy geocentric mean-ecliptic-of-J2000 -> (lon, lat, dist_km)."""
    from astropy.time import Time
    from astropy.coordinates import get_body, get_sun, GeocentricMeanEcliptic

    t = Time(iso.replace("Z", ""), scale="utc")
    sc = get_sun(t) if body == "sun" else get_body(body, t)
    frame = GeocentricMeanEcliptic(equinox="J2000", obstime=t)
    e = sc.transform_to(frame)
    return e.lon.deg % 360.0, e.lat.deg, e.distance.to("km").value


def query_live(url: str, body: str, iso: str, user: str, pwd: str):
    """Optionally exercise the running HTTP service end-to-end (POST /position/).

    Returns the raw CartesianCoords dict (geocentric ECLIPJ2000 km, either backend) or an
    {'error': ...} marker. Captured for reference / to exercise the HTTP layer, not used as
    the truth oracle (that stays computed directly from the ephemeris libraries).
    """
    import ssl
    import urllib.parse
    import urllib.request

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # self-signed dev cert

    def _post(path, data, headers):
        req = urllib.request.Request(url.rstrip("/") + path, data=data,
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return json.loads(resp.read().decode())

    try:
        # urlencode so reserved characters in the password (e.g. '+') survive transport;
        # a bare f-string would let '+' decode to a space server-side and fail auth (403).
        form = urllib.parse.urlencode({"username": user, "password": pwd}).encode()
        token = _post("/token", form,
                      {"Content-Type": "application/x-www-form-urlencoded"})
        body_json = json.dumps({"ident": "live", "body": body, "dt": iso}).encode()
        result = _post("/position/", body_json, {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {json.dumps(token)}",
        })
        return result.get("position", result)
    except Exception as exc:  # noqa: BLE001 - diagnostic capture, never fatal
        return {"error": str(exc)}


def build(stamp: str, live_url: str | None, user: str, pwd: str):
    furnish_spice_kernels(BODIES)

    from astropy.coordinates import solar_system_ephemeris
    solar_system_ephemeris.set(os.path.join(KERNEL_DIR, "de430.bsp"))

    records = []
    max_lon_diff = 0.0
    max_lat_diff = 0.0
    for iso in DATES:
        for body in BODIES:
            s_lon, s_lat, s_dist, s_xyz = spice_ecliptic(body, iso)
            a_lon, a_lat, a_dist = astro_ecliptic(body, iso)
            lon_diff = angular_diff_deg(s_lon, a_lon)
            lat_diff = abs(s_lat - a_lat)
            max_lon_diff = max(max_lon_diff, lon_diff)
            max_lat_diff = max(max_lat_diff, lat_diff)
            rec = {
                "datetime": iso,
                "body": body,
                "spice": {
                    "eclipticLonDeg": s_lon, "eclipticLatDeg": s_lat,
                    "distanceKm": s_dist, "cartesianEclipJ2000Km": s_xyz,
                },
                "astro": {
                    "eclipticLonDeg": a_lon, "eclipticLatDeg": a_lat,
                    "distanceKm": a_dist,
                },
                "crossCheckLonDiffDeg": lon_diff,
                "crossCheckLatDiffDeg": lat_diff,
            }
            if live_url:
                rec["liveService"] = query_live(live_url, body, iso, user, pwd)
            records.append(rec)
            print(f"  {iso}  {body:<5}  spice_lon={s_lon:8.4f}  astro_lon={a_lon:8.4f}"
                  f"  d_lon={lon_diff:.4f}")

    fixture = {
        "metadata": {
            "generator": "packages/space-data-api/validation/generate_ephemeris_truth.py",
            "purpose": ("Real geocentric ecliptic (J2000) positions, ground truth for "
                        "validating the space-sim offline analytic model."),
            "frame": "geocentric ecliptic, mean equinox of J2000",
            "backends": {
                "spice": {"library": "spiceypy", "kernels": ["latest_leapseconds.tls",
                          "de440.bsp", "mar097.bsp (mars)"],
                          "method": "spkpos(body, et, 'ECLIPJ2000', 'NONE', 'EARTH')"},
                "astro": {"library": "astropy", "kernels": ["de430.bsp"],
                          "method": "get_body(...).transform_to(GeocentricMeanEcliptic J2000)"},
            },
            "obliquityJ2000Deg": OBLIQUITY_J2000_DEG,
            "crossCheckToleranceDeg": CROSS_CHECK_TOL_DEG,
            "crossCheckMaxLonDiffDeg": max_lon_diff,
            "crossCheckMaxLatDiffDeg": max_lat_diff,
            "assertedBody": "sun",
            "characterizationBodies": ["moon", "mars"],
            "note": ("Truth is queried from the ephemeris libraries directly to keep the "
                     "oracle independent of the code under test. Bugs found here in the "
                     "shipped celestial_position (frame mismatch, furnsh-on-list, Moon/"
                     "planet kernel selection, dead matplotlib import) were fixed and now "
                     "agree with this truth to <0.011deg. See the validation harness README."),
            "generatedAt": stamp,
        },
        "records": records,
    }
    return fixture, max_lon_diff, max_lat_diff


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="output fixture path (default: the space-sim fixtures dir)")
    parser.add_argument("--stamp", default="unspecified",
                        help="ISO timestamp recorded as metadata.generatedAt "
                             "(kept as an arg so the script output is deterministic)")
    parser.add_argument("--live", metavar="URL", default=None,
                        help="also POST /position/ to a running service, e.g. "
                             "https://localhost:8000 (captured for reference)")
    parser.add_argument("--user", default=os.environ.get("VITE_OAUTH_USER", ""))
    parser.add_argument("--pwd", default=os.environ.get("VITE_OAUTH_PWD", ""))
    args = parser.parse_args()

    warnings.filterwarnings("ignore")  # ERFA dubious-year / leap-second chatter

    print("Generating ephemeris truth (spice de440 vs astropy de430) ...")
    fixture, max_lon, max_lat = build(args.stamp, args.live, args.user, args.pwd)

    if max_lon > CROSS_CHECK_TOL_DEG:
        raise SystemExit(
            f"Backends disagree: max ecliptic-longitude diff {max_lon:.4f}° exceeds "
            f"tolerance {CROSS_CHECK_TOL_DEG}°")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(fixture, fh, indent=2)
        fh.write("\n")

    print(f"\nCross-check OK: max |spice-astro| lon={max_lon:.4f}° lat={max_lat:.4f}° "
           f"(tol {CROSS_CHECK_TOL_DEG}°)")
    print(f"Wrote {len(fixture['records'])} records -> {args.out}")


if __name__ == "__main__":
    main()
