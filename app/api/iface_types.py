from typing import Annotated, Union, Literal

from fastapi import Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, AwareDatetime, Field

from .abstract_query import Vector3, LatLonAlt, RaDec, u, CoordRefFrame, Position


class CartesianCoords(BaseModel):
    coord_type: Literal["cartesian"] = "cartesian"
    x: float
    y: float
    z: float
    units: str

    class Config:
        extra = 'forbid'

    def to_vector(self):
        return Vector3(self.x * u(self.units), self.y * u(self.units), self.z * u(self.units))

    @classmethod
    def from_vector(cls, v: Vector3):
        assert v.x.units == v.y.units and v.y.units == v.z.units
        return cls(x=v.x.magnitude, y=v.y.magnitude, z=v.z.magnitude, units=str(v.z.units))


class SphericalCoords(BaseModel):
    coord_type: Literal["spherical"] = "spherical"
    lat: float
    lon: float
    alt: float
    units: str

    class Config:
        extra = 'forbid'

    def to_lla(self):
        return LatLonAlt(lat=self.lat * u.degrees, lon=self.lon * u.degrees, alt=self.alt * u(self.units))

    def to_radec(self):
        return RaDec(dec=self.lat * u.degrees, ra=self.lon * u.degrees, dist=self.alt * u(self.units))

    @classmethod
    def from_lla(cls, lla: LatLonAlt):
        assert lla.lat.units == u.degree and lla.lon.units == u.degree
        return cls(lat=lla.lat.magnitude, lon=lla.lon.magnitude, alt=lla.alt.magnitude, units=str(lla.alt.units))

    @classmethod
    def from_radec(cls, rdd: RaDec):
        assert rdd.ra.units == u.degree and rdd.dec.units == u.degree
        return cls(ra=rdd.ra.magnitude, dec=rdd.dec.magnitude, alt=rdd.dist.magnitude, units=str(rdd.dist.units))


def transfer_coords(coords: Position, klass: LatLonAlt|RaDec = LatLonAlt):
    if isinstance(coords, LatLonAlt):
        return SphericalCoords.from_lla(coords)
    if isinstance(coords, RaDec):
        return SphericalCoords.from_radec(coords)
    if isinstance(coords, SphericalCoords):
        if klass == LatLonAlt:
            return coords.to_lla()
        return coords.to_radec()
    if isinstance(coords, Vector3):
        return CartesianCoords.from_vector(coords)
    if isinstance(coords, CartesianCoords):
        return coords.to_vector()


class ErrorResp(BaseModel):
    resp_type: Literal["error"] = "error"
    ident: str
    error: str


AuthReq = Annotated[OAuth2PasswordRequestForm, Depends()]

class AuthToken(BaseModel):
    access_token: str
    token_type: str


class ConversionReq(BaseModel):
    ident: str
    coords: Union[CartesianCoords, SphericalCoords] = Field(discriminator='coord_type')
    original: CoordRefFrame
    new: CoordRefFrame
    dt: AwareDatetime


class ConversionResp(BaseModel):
    resp_type: Literal["data"] = "data"
    ident: str
    coordinates: Union[CartesianCoords, SphericalCoords] = Field(discriminator='coord_type')


ConversionOrErrorResp = Union[ConversionResp, ErrorResp]
#class ConversionOrErrorResp(BaseModel):
#    discrim: Union[ConversionResp, ErrorResp] = Field(discriminator='resp_type')


class T2CConversionReq(BaseModel):
    ident: str
    coords: SphericalCoords
    dt: AwareDatetime


class C2TConversionReq(BaseModel):
    ident: str
    coords: CartesianCoords
    dt: AwareDatetime


class PositionReq(BaseModel):
    ident: str
    body: str
    dt: AwareDatetime


class PositionResp(BaseModel):
    resp_type: Literal["data"] = "data"
    ident: str
    position: CartesianCoords


PositionOrErrorResp = Union[PositionResp, ErrorResp]
#class PositionOrErrorResp(BaseModel):
#    discrim: Union[PositionResp, ErrorResp] = Field(discriminator='resp_type')
