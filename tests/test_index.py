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

"""Endpoint tests for api.index, exercising the (default 'astro') SpaceQuery backend
against the real SPICE/ephemeris kernels in app/kernels.

The endpoint functions take a single pydantic request model and are called directly
(the auth dependency is a route decorator, so it is not enforced when calling the
coroutine itself). Geocentric ECLIPJ2000 truth used for the tolerances is cross-checked
in packages/space-data-api/validation/ and the space-sim ephemeris fixture.
"""

import math
from datetime import datetime, UTC

import pytest

from api.index import body_position, convert_coords, terr2cele, cele2terr
from api.iface_types import (PositionReq, ConversionReq, T2CConversionReq, C2TConversionReq,
                             CartesianCoords, SphericalCoords)
from api.space_query import SpaceQuery

DT = datetime(2024, 7, 25, 14, 30, 0, tzinfo=UTC)
AU_KM = 1.495978707e8


def _radius(p):
    return math.sqrt(p.x ** 2 + p.y ** 2 + p.z ** 2)


def _ecliptic_lon_lat(p):
    r = _radius(p)
    return math.degrees(math.atan2(p.y, p.x)) % 360.0, math.degrees(math.asin(p.z / r))


@pytest.mark.asyncio
async def test_body_position_sun_is_ecliptic_and_one_au():
    resp = await body_position(PositionReq(ident='sun', body='sun', dt=DT))
    pos = resp.position
    assert pos.coord_type == 'cartesian'
    assert pos.units == 'kilometer'
    lon, lat = _ecliptic_lon_lat(pos)
    assert abs(_radius(pos) - 1.0157 * AU_KM) < 0.01 * AU_KM   # ~1.016 AU late July
    assert abs(lat) < 0.5                                      # Sun rides the ecliptic
    assert 121.0 < lon < 124.0                                 # geocentric ecliptic lon ~122.8 deg


@pytest.mark.asyncio
async def test_body_position_moon_is_near_earth():
    resp = await body_position(PositionReq(ident='moon', body='moon', dt=DT))
    # The Moon is ~0.36-0.41 Gm from Earth — far closer than any heliocentric body.
    assert 3.5e5 < _radius(resp.position) < 4.1e5


@pytest.mark.asyncio
async def test_body_position_invalid_returns_error():
    resp = await body_position(PositionReq(ident='bad', body='not-a-body', dt=DT))
    assert resp.resp_type == 'error'
    assert 'Invalid' in resp.error


@pytest.mark.asyncio
async def test_convert_cartesian_rotation_preserves_norm():
    coords = CartesianCoords(x=4.0, y=5.0, z=6.0, units='km')
    resp = await convert_coords(
        ConversionReq(ident='cvt', coords=coords, original='ITRF93', new='J2000', dt=DT))
    out = resp.coordinates
    # A frame change is a rotation: same form (cartesian), same length, but moved.
    assert out.coord_type == 'cartesian'
    assert math.isclose(_radius(out), math.sqrt(4 ** 2 + 5 ** 2 + 6 ** 2), rel_tol=1e-9)
    assert (abs(out.x - 4) + abs(out.y - 5) + abs(out.z - 6)) > 1e-6  # actually rotated


@pytest.mark.asyncio
async def test_terrestrial_celestial_round_trip():
    lat, lon, alt = 35.2, 106.3, 7000.0
    fwd = await terr2cele(
        T2CConversionReq(ident='t2c',
                         coords=SphericalCoords(lat=lat, lon=lon, alt=alt, units='km'), dt=DT))
    cele = fwd.coordinates
    assert cele.coord_type == 'cartesian'
    back = await cele2terr(
        C2TConversionReq(ident='c2t',
                         coords=CartesianCoords(x=cele.x, y=cele.y, z=cele.z, units=cele.units),
                         dt=DT))
    lla = back.coordinates
    assert lla.coord_type == 'spherical'
    assert math.isclose(lla.lat, lat, abs_tol=1e-6)
    assert math.isclose(((lla.lon - lon + 180) % 360) - 180, 0.0, abs_tol=1e-6)
    assert math.isclose(lla.alt, alt, abs_tol=1e-3)


@pytest.mark.asyncio
async def test_spice_and_astro_backends_agree_on_sun():
    # Both shipped backends must now return the same geocentric ECLIPJ2000 vector.
    spice = SpaceQuery.get_impl('spice').celestial_position('sun', DT)
    astro = SpaceQuery.get_impl('astro').celestial_position('sun', DT)
    a = [spice.x.magnitude, spice.y.magnitude, spice.z.magnitude]
    b = [astro.x.magnitude, astro.y.magnitude, astro.z.magnitude]
    cos = sum(i * j for i, j in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))
    assert math.degrees(math.acos(min(1.0, cos))) < 0.02  # agree to <0.02 deg
