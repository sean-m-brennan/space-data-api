import os
from datetime import datetime

from astropy import coordinates
from astropy.coordinates import SkyCoord, WGS84GeodeticRepresentation, solar_system_ephemeris
from astropy.time import Time
from astropy.units import Quantity

from .abstract_query import AbsSpaceQuery, Position, CoordRefFrame, LatLonAlt, RaDec, Vector3, ureg
from.naif_ids import NAIF_IDS


class AstroQuery(AbsSpaceQuery):
    kernel_cache = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')

    def __init__(self, _jit: bool = False):
        super().__init__()
        solar_system_ephemeris.set('jpl')
        solar_system_ephemeris.set(os.path.join(self.kernel_cache, 'de430.bsp'))

    @classmethod
    def astro_quant_to_pint(cls, quant: Quantity):
        return ureg.Quantity(quant.value, quant.unit.name)

    @classmethod
    def crf_to_astro_repr(cls, crf: CoordRefFrame) -> str:
        return crf.value

    def transform_coordinates(self, position: Position, original: str, new: str, dt: datetime) -> Position:
        orig_frame = self.crf_to_astro_repr(self._validate_frame(original))
        new = self._validate_frame(new)
        new_frame = self.crf_to_astro_repr(new)
        sc = SkyCoord(*(position.to_list()[:2]), frame=orig_frame, unit='deg')
        xform = sc.transform_to(new_frame)
        if new == CoordRefFrame.ITRF:
            return LatLonAlt(xform.lat, xform.lon, xform.height)
        return RaDec(xform.ra, xform.dec, xform.height)

    def celestial_position(self, body: str, dt: datetime)-> Vector3:
        if body.upper() not in NAIF_IDS:
            raise RuntimeError('Invalid celestial body: %s' % body)
        # FIXME convert dt
        if body.upper() == 'SUN':
            sc = coordinates.get_sun(Time(dt))
        else:
            sc = coordinates.get_body(body, Time(dt))  # in GCRS frame
        #wgs = sc.transform_to(WGS84GeodeticRepresentation)  # doesn't work
        #return self._spherical_to_cartesian(LatLonAlt(wgs.lat, wgs.lon, wgs.height))
        dec_ra_dist = map(self.astro_quant_to_pint, [sc.dec, sc.ra, sc.distance])
        return self._spherical_to_cartesian(RaDec(*dec_ra_dist))
