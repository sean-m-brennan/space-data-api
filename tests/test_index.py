import json

import pytest

from app.api.index import convert_coords, fixed_to_j2k, body_position


@pytest.mark.asyncio
async def test_convert_coords():
    actual = await convert_coords(1, '[4, 5, 6]', 'ITRF93', 'J2000', '2022-07-25T14:30:00')
    if 'error' in actual:
        print(actual['error'])
    expected = {'id': 1, 'coordinates': [-5.426920120205441, -3.3772860286513966, 6.011861366464254]}
    assert actual == expected


@pytest.mark.asyncio
async def test_fixed_to_j2k():
    actual = await fixed_to_j2k(2, 35.2, 106.3, 7000.0, '2024-07-25T14:30:00')
    if 'error' in actual:
        print(actual['error'])
    expected = {"id": 2, "coordinates": [-500.9971855912586, -10919.268847069785, 7713.178285000932]}
    assert actual == expected


@pytest.mark.asyncio
async def test_error():
    actual = await convert_coords(3, '[4, 5, 6]', 'ITRF93', 'J2000', 'abc')
    if 'error' in actual:
        print(actual['error'])
    expected = {"id": 3, "error": "Invalid isoformat string: 'abc'"}
    assert actual == expected


@pytest.mark.asyncio
async def test_convert_radec():
    actual = await convert_coords(4, '[180.0, 89.0]', 'IAU_EARTH', 'J2000', '2024-07-25T14:30:00')
    if 'error' in actual:
        print(actual['error'])
    expected = {"id": 4, "coordinates": [-500.9971855912586, -10919.268847069785, 7713.178285000932]}
    # TODO support other coord sys conversions
    expected = {"id": 4, "error": "Unsupported conversion IAU_EARTH => J2000"}
    assert actual == expected


@pytest.mark.asyncio
async def test_body_position():
    actual = await body_position(5, 'sun', '2024-07-25T14:30:00')
    if 'error' in actual:
        print(actual['error'])
    expected = {"id": 5, "position": [-82298877.08640607, 117186209.91842905, 50799053.065901026]}
    assert actual == expected
