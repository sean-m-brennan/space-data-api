import os
from datetime import datetime

from astropy import coordinates
from astropy.coordinates import SkyCoord, solar_system_ephemeris
from astropy.time import Time
from astropy.units import Quantity, dimensionless_unscaled

from .abstract_query import AbsSpaceQuery, Position, CoordRefFrame, LatLonAlt, RaDec, Vector3, u
from .naif_ids import NAIF_IDS


class AstroQuery(AbsSpaceQuery):
    kernel_cache = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')

    def __init__(self, _jit: bool = False):
        super().__init__()
        solar_system_ephemeris.set(os.path.join(self.kernel_cache, 'de430.bsp'))

    @classmethod
    def astro_quant_to_pint(cls, quant: Quantity):
        try:
            units = quant.units  # actually, it's pint
        except AttributeError:
            units = quant.unit.to_string()
        return u.Quantity(quant.value, units)

    @classmethod
    def crf_to_astro_repr(cls, crf: CoordRefFrame) -> str:
        if crf == CoordRefFrame.ITRF:
            return 'itrs'
        if crf == CoordRefFrame.ICRF:
            return 'icrs'
        if crf == CoordRefFrame.ECLIPJ2K:
            return 'gcrs'
        return crf.value

    def transform_coordinates(self, position: Position, original: str, new: str, dt: datetime) -> Position:
        orig_frame = self.crf_to_astro_repr(self._validate_frame(original))
        new = self._validate_frame(new)
        new_frame = self.crf_to_astro_repr(new)
        pos = position.from_center()
        unit = pos[2].units
        sc = SkyCoord(*pos, frame=orig_frame)
        xform = sc.transform_to(new_frame)
        if new == CoordRefFrame.ITRF:
            height = xform.height
            if xform.height.unit == dimensionless_unscaled:
                height *= unit
            lla = list(map(self.astro_quant_to_pint, [xform.lat, xform.lon, height]))
            return LatLonAlt(*lla)

        distance = xform.distance
        if xform.distance.unit == dimensionless_unscaled:
            distance *= unit
        dec_ra_dist = list(map(self.astro_quant_to_pint, [xform.dec, xform.ra, distance]))
        return RaDec(*dec_ra_dist)

    def celestial_position(self, body: str, dt: datetime)-> Vector3:
        if body.upper() not in NAIF_IDS:
            raise RuntimeError('Invalid celestial body: %s' % body)
        if body.upper() == 'SUN':
            sc = coordinates.get_sun(Time(dt))
        else:
            sc = coordinates.get_body(body, Time(dt))  # in GCRS frame
        #wgs = sc.transform_to(WGS84GeodeticRepresentation)  # doesn't work
        #return self._spherical_to_cartesian(LatLonAlt(wgs.lat, wgs.lon, wgs.height))
        dec_ra_dist = map(self.astro_quant_to_pint, [sc.dec, sc.ra, sc.distance])
        return self._spherical_to_cartesian(RaDec(*dec_ra_dist))
