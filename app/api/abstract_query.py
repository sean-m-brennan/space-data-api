# -*- coding: utf-8 -*-

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

from abc import abstractmethod, ABC
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math

try:
    from typing import Type, TypeVar
except ImportError:
    from typing_extensions import Type, TypeVar

import pint

u = pint.UnitRegistry()
Quant = u.Quantity

earth_radius = 6371.

class Point(ABC):
    @abstractmethod
    def to_list(self):
        pass

    def from_center(self):
        return self.to_list()


@dataclass
class Vector3(Point):
    """ Generic three-dimensional vector, with length units """
    x: Quant  # length
    y: Quant  # length
    z: Quant  # length

    def to_list(self):
        return [self.x, self.y, self.z]


@dataclass
class Matrix3:
    a: Vector3
    b: Vector3
    c: Vector3


@dataclass
class RaDec(Point):
    """ Right Ascension/Declination in decimal degrees, with Altitude """
    dec: Quant  # degree
    ra: Quant  # degree
    alt: Quant  # length

    def to_list(self):
        return [self.dec, self.ra, self.alt]


@dataclass
class LatLonAlt(Point):
    """ Longitude/Latitude/Altitude in decimal degrees """
    lat: Quant  # degree
    lon: Quant  # degree
    alt: Quant  # length

    def to_list(self):
        return [self.lat, self.lon, self.alt]

    def from_center(self):
        return [self.lat, self.lon, self.alt + (earth_radius * u.km)]


Position = Vector3 | RaDec | LatLonAlt


class CoordRefFrame(str, Enum):
    """ Supported reference frames"""
    ICRF = 'J2000'           # celestial, equatorial, Earth-centered - Ra/Dec
    ECLIPJ2K = 'ECLIPJ2000'  # celestial, ecliptic, Earth-centered - LatLon
    ITRF = 'ITRF93'          # terrestrial, equatorial, fixed - LatLon
    IAU_SUN = 'IAU_SUN'
    IAU_MOON = 'IAU_MOON'
    IAU_MARS = 'IAU_MARS'

    @staticmethod
    def aliases():
        forward = {
            CoordRefFrame.ICRF: ['ICRS', 'ICRF', 'EME2000', 'EME2K', 'J2000', 'J2K', 'ECI'],
            CoordRefFrame.ECLIPJ2K: ['ECLIPJ2000', "GCRS"],
            CoordRefFrame.ITRF: ['ITRF', 'ITRF93', 'IAU_EARTH', 'ECEF'],
            CoordRefFrame.IAU_SUN: ['IAU_SUN'],
            CoordRefFrame.IAU_MOON: ['IAU_MOON'],
            CoordRefFrame.IAU_MARS: ['IAU_MARS'],
        }
        return {v: k for k, vs in forward.items() for v in vs}


class AbsSpaceQuery:
    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def celestial_position(self, body: str, dt: datetime) -> Vector3:
        """
        For a given date/time, retrieve the position of the given celestial body (in *cartesian* ECLIPJ2K).
        :param body: string in NAIF_IDS
        :param dt: datetime
        :return: 3D vector
        """
        raise NotImplementedError

    @abstractmethod
    def transform_coordinates(self, position: Position, original: CoordRefFrame|str,
                              new: CoordRefFrame|str, dt: datetime) -> Position:
        """
        For a given date/time, convert from one coordinate system to another.
        Results will be in the same form as the input position: cartesian (Vector3) or polar (RaDec or LatLonAlt).
        For clarity with polar positions, RaDec is strictly celestial and LatLonAlt is strictly terrestrial.
        :param position: Vector3 or RaDec or LatLonAlt
        :param original: CoordRefFrame
        :param new: CoordRefFrame
        :param dt: datetime in UTC
        :return: Vector3 or RaDec or LatLonAlt
        """
        raise NotImplementedError

    def terrestrial_to_celestial(self, position: LatLonAlt, dt: datetime) -> Vector3:
        """Convenience function for converting ECEF coordinates to *cartesian* ECLIPJ2K"""
        return self._spherical_to_cartesian(
            self.transform_coordinates(position, CoordRefFrame.ITRF, CoordRefFrame.ECLIPJ2K, dt))

    def celestial_to_terrestrial(self, position: Vector3, dt: datetime) -> LatLonAlt:
        """Convenience function for converting *cartesian* ECLIPJ2K coordinates to ECEF"""
        return self.transform_coordinates(self._cartesian_to_polar(position),
                                          CoordRefFrame.ECLIPJ2K, CoordRefFrame.ITRF, dt)

    @classmethod
    def _validate_frame(cls, frame: CoordRefFrame|str) -> CoordRefFrame:
        if isinstance(frame, CoordRefFrame):
            new_frame = frame
        else:
            new_frame = cls._string_to_coord_ref_frame(frame)
        return new_frame

    @staticmethod
    def _string_to_coord_ref_frame(frame: str) -> CoordRefFrame:
        try:
            return CoordRefFrame.aliases()[frame]
        except KeyError:
            raise RuntimeError("Unsupported coordinate reference frame: %s" % frame)

    @staticmethod
    def _spherical_to_cartesian(position: LatLonAlt|RaDec) -> Vector3:
        pos_vec = position.to_list()
        [phi, rho, dist] = map(lambda n: n.magnitude * (math.pi / 180.), pos_vec)
        x = dist * math.cos(phi) * math.cos(rho) * pos_vec[2].units # greenwich at equator
        y = dist * math.cos(phi) * math.sin(rho) * pos_vec[2].units
        z = dist * math.sin(phi)  * pos_vec[2].units # through poles
        return Vector3(x, y, z)  # units are automatic from dist

    T = TypeVar('T', bound=LatLonAlt|RaDec)

    @staticmethod
    def _cartesian_to_polar(position: Vector3, klass: Type[T] = LatLonAlt) -> T:
        unit = position.z.units
        dist = math.sqrt(position.x.magnitude**2 + position.y.magnitude**2 + position.z**2)
        rho = math.atan2(position.y.magnitude, position.x.magnitude)
        phi = math.asin(position.z.magnitude / dist)
        if rho > 2 * math.pi:
            rho = rho - 2 * math.pi
        elif rho < -2 * math.pi:
            rho = rho + 2 * math.pi
        phi, rho = map(lambda n: n * (180. / math.pi) * u.degrees, [phi, rho])
        return klass(phi, rho, dist * unit)
