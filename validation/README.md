# Ephemeris validation harness

Validates the **space-sim offline analytic propagation model** against *real* ephemeris
positions. It is the live counterpart to the formula-oracle suite in
`packages/space-sim/test/planetarium/ephemeris_validation.test.ts`.

## How it fits together

```
generate_ephemeris_truth.py            (this dir, Python)
   │  queries two independent ephemeris sources behind space-data-api:
   │    • spiceypy + app/kernels/de440.bsp   →  spkpos(..., 'ECLIPJ2000', 'NONE', 'EARTH')
   │    • astropy  + app/kernels/de430.bsp   →  GeocentricMeanEcliptic(J2000)
   │  reduces both to canonical geocentric ecliptic lon/lat, cross-checks agreement
   ▼
packages/space-sim/test/planetarium/fixtures/ephemeris_truth.json   (committed)
   ▼
packages/space-sim/test/planetarium/ephemeris_validation_live.test.ts   (vitest)
      diffs EarthConsts.solarPosition against the fixture truth (Sun: hard tolerances;
      Moon/Mars: characterization only).
```

The fixture is committed, so the vitest suite runs in CI **without** the Python service.
Regenerate the fixture only when the bodies/dates/tolerances change.

## Setup (one-time)

The generator's deps are not the conda-only set in `environment.yml`, so use a plain venv:

```bash
cd packages/space-data-api
df -h .                                   # confirm <90% used before installing
uv venv .venv
uv pip install --python .venv/bin/python -r validation/requirements-validation.txt
```

SPICE kernels must already be present in `app/kernels/` (de430/de440, leapseconds,
`mar097.bsp` for Mars). See `app/download_kernels.py` if they are missing.

## Regenerate the fixture

```bash
cd packages/space-data-api
.venv/bin/python validation/generate_ephemeris_truth.py --stamp "$(date -u +%FT%TZ)"
```

It prints each (date, body) longitude from both sources, then asserts the two agree to
within `crossCheckToleranceDeg` (0.05°) before writing the fixture. Then verify the model:

```bash
cd packages/space-sim && npm test -- ephemeris_validation_live
```

## What the harness establishes

| Check (Sun) | Tolerance | Observed |
|-------------|-----------|----------|
| spice vs astro backend agreement | < 0.05° | ~0.01° |
| quarterly longitude **advance** vs real | < 0.5° | ~0.02° |
| **anchor** offset at the vernal equinox | < 3° | ~2.57° |
| max instantaneous offset across 2025 | < 3° | ~2.59° |

- The ~2.6° anchor offset (the model's fixed integer-DOY-79 equinox + true/mean Sun) is the
  live refinement of the doc's formula-based "~2°" estimate.
- The J2000 reference epoch is logged (not asserted) at ~3.15°, quantifying the secular
  drift of the fixed-DOY anchor (~0.6° / 25 yr).
- Moon/Mars absolute positions are recorded as ground truth but not asserted — the offline
  model does not anchor them (gap by design; see the validation doc).

## Optional: end-to-end against a running service (`--live`)

To additionally exercise the live HTTP layer (token auth + self-signed cert + `/position/`).
Running the service needs the runtime deps, so use `requirements-test.txt` (it pins `libpass`
+ `uvicorn`; stock `passlib` 1.7.4 crashes against `bcrypt>=4.1`):

```bash
cd packages/space-data-api
uv pip install --python .venv/bin/python -r validation/requirements-test.txt

# terminal 1 — start the service (uses app/cert.pem, app/key.pem)
.venv/bin/uvicorn main:app --app-dir app --host 127.0.0.1 --port 8000 \
    --ssl-keyfile app/key.pem --ssl-certfile app/cert.pem

# terminal 2 — capture raw service responses alongside the truth
set -a; . ./.env; set +a            # VITE_OAUTH_USER / VITE_OAUTH_PWD
.venv/bin/python validation/generate_ephemeris_truth.py --live https://127.0.0.1:8000 \
    --stamp "$(date -u +%FT%TZ)" --out /tmp/ephemeris_truth_live.json
```

Each record gains a `liveService` field. The generator computes truth from the ephemeris
libraries directly (not via the service) so the oracle stays independent of the code under
test; `--live` is for inspecting the raw HTTP responses. Verified end-to-end: all 57 records
returned over HTTPS match the spice truth to <0.011° (`/convert`, `/terrestrial2celestial`,
`/celestial2terrestrial` round-trip correctly too).

## Service-code fixes

Validating the harness surfaced bugs in the shipped backends, all now **fixed and verified**.

### Position (`celestial_position`) — agree with the harness truth to <0.011°

| File | Bug | Fix |
|------|-----|-----|
| `app/api/abstract_query.py` | dead `astropy.visualization.wcsaxes` import dragged in matplotlib | removed the import |
| `app/api/astro_converter.py` | `celestial_position` returned an **equatorial** vector (GCRS ra/dec) — inconsistent with the spice path | transform to `GeocentricMeanEcliptic(J2000)`, return cartesian km |
| `app/api/spice_converter.py` | `_init_kernels` called `furnsh()` on the planets-kernel **list**; `celestial_position` fed the cartesian `spkpos` result through `_spherical_to_cartesian` | resolve list→files; return the `spkpos` vector directly as km |
| `app/api/spice_converter.py` | kernel **selection** loaded no ephemeris for the Moon, used a wrong-case satellite key, and omitted the planet-body SPK (Mars 499 ∈ `mar097.bsp`) | load `spk/planets` for the Moon; lowercase satellite keys; load the per-planet SPK for planet bodies |

### Coordinate transforms (`transform_coordinates` + convenience methods)

The whole ITRF↔ECLIPJ2000↔J2000 path was broken; redesigned to a single contract — *input
form is preserved* (cartesian→cartesian; polar→polar, in the representation natural to the
target frame: terrestrial→`LatLonAlt`, celestial→`RaDec`). Verified: `terr→cele→terr`
round-trips to ~1e-13, the spice rotation matches astropy to **0.0000°** (~1 m), and the
spice and astro backends agree to **0.0000°**.

| File | Bug | Fix |
|------|-----|-----|
| `app/api/abstract_query.py` | `_spherical_to_cartesian` scaled the **distance** by `π/180` (every vector ~57× too short) | only the two angles convert to radians; distance kept; uses `from_center()` so `LatLonAlt` altitude → geocentric radius |
| `app/api/abstract_query.py` | `_cartesian_to_polar` used `position.z**2` (a `km²` quantity) → `DimensionalityError` on **every** call | `.magnitude` on `z`; strip `earth_radius` for a terrestrial `LatLonAlt` result |
| `app/api/{spice,astro}_converter.py` | `transform_coordinates` rotated polar `[lat,lon,alt]` **as if cartesian** (and fed pint quantities to `np.dot`); astro mapped ECLIPJ2K → `gcrs` (equatorial) | reduce polar→cartesian first, rotate (`spice.pxform` / astropy `GCRS`·`ITRS`·`GeocentricMeanEcliptic`), return in the input's form |
| `app/api/abstract_query.py` | `terrestrial_to_celestial` / `celestial_to_terrestrial` built on the above — broken end-to-end (this backs the app's `fixedToJ2000`) | rewritten symmetrically on the corrected `transform_coordinates` |

### Tests

`tests/test_index.py` was rewritten against the current pydantic-model endpoint API (it
previously imported a removed `fixed_to_j2k` and used an old positional-arg signature). Run:

```bash
uv pip install --python .venv/bin/python -r validation/requirements-test.txt
.venv/bin/python -m pytest          # 6 passed
```
