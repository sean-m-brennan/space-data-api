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

import os
from datetime import datetime

import astropy.units as au
from astropy import coordinates
from astropy.coordinates import (solar_system_ephemeris, GeocentricMeanEcliptic, GCRS, ITRS,
                                 CartesianRepresentation)
from astropy.time import Time

from .abstract_query import AbsSpaceQuery, Position, CoordRefFrame, LatLonAlt, RaDec, Vector3, u
from .naif_ids import NAIF_IDS


class AstroQuery(AbsSpaceQuery):
    kernel_cache = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')

    def __init__(self, _jit: bool = False):
        super().__init__()
        solar_system_ephemeris.set(os.path.join(self.kernel_cache, 'de430.bsp'))

    @classmethod
    def _astro_frame(cls, crf: CoordRefFrame, t: Time):
        """Map a CoordRefFrame to the equivalent geocentric astropy frame at epoch t."""
        if crf == CoordRefFrame.ITRF:
            return ITRS(obstime=t)                                      # terrestrial, earth-fixed
        if crf == CoordRefFrame.ICRF:
            return GCRS(obstime=t)                                      # celestial, equatorial J2000
        if crf == CoordRefFrame.ECLIPJ2K:
            return GeocentricMeanEcliptic(equinox='J2000', obstime=t)   # celestial, ecliptic J2000
        raise RuntimeError('Unsupported coordinate reference frame: %s' % crf)

    def transform_coordinates(self, position: Position, original: str, new: str, dt: datetime) -> Position:
        orig_frame = self._validate_frame(original)
        new_frame = self._validate_frame(new)
        # Same contract as the SPICE backend: reduce polar input to a cartesian vector,
        # rotate between geocentric frames with astropy, return in the input's form (a
        # polar input yields the representation natural to the target frame).
        is_polar = not isinstance(position, Vector3)
        cart = self._spherical_to_cartesian(position) if is_polar else position
        unit = cart.z.units
        aq = au.Unit(str(unit))
        t = Time(dt)
        rep = CartesianRepresentation(cart.x.magnitude * aq, cart.y.magnitude * aq, cart.z.magnitude * aq)
        src = self._astro_frame(orig_frame, t).realize_frame(rep)
        out = src.transform_to(self._astro_frame(new_frame, t)).cartesian
        rotated = Vector3(out.x.to(aq).value * unit, out.y.to(aq).value * unit, out.z.to(aq).value * unit)
        if not is_polar:
            return rotated
        klass = LatLonAlt if new_frame == CoordRefFrame.ITRF else RaDec
        return self._cartesian_to_polar(rotated, klass)

    def celestial_position(self, body: str, dt: datetime)-> Vector3:
        if body.upper() not in NAIF_IDS:
            raise RuntimeError('Invalid celestial body: %s' % body)
        t = Time(dt)
        if body.upper() == 'SUN':
            sc = coordinates.get_sun(t)
        else:
            sc = coordinates.get_body(body, t)  # in GCRS frame
        # Return a *cartesian* ECLIPJ2000 (geocentric, mean ecliptic & equinox of J2000)
        # vector in km — the contract shared with the SPICE backend. The GCRS ra/dec are
        # equatorial, so transform to the ecliptic frame before taking the cartesian.
        cart = sc.transform_to(GeocentricMeanEcliptic(equinox='J2000', obstime=t)).cartesian
        return Vector3(cart.x.to('km').value * u.km,
                       cart.y.to('km').value * u.km,
                       cart.z.to('km').value * u.km)
