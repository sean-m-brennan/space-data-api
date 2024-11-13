#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import glob
import math
import re
from datetime import datetime
import urllib.request

import requests
from bs4 import BeautifulSoup
import numpy as np
import spiceypy as spice

from .naif_ids import PLANETS, SATELLITES_PLANET


JGM3Re: float = 6378.137
KERNELS: dict[str, str | dict[str, str | dict[str, str]]] = {
    'lsk': 'latest_leapseconds.tls',  # time
    'tpc': 'pck00010.tpc',  # orientation
    'tf': 'earth_assoc_itrf93.tf',  # reference frame
    'pck': { # planet constants
        'earth': 'earth_1962_240827_2124_combined.bpc',
        'moon': 'moon_pa_de440_200625.bpc',
    },
    'spk': {  # planetary ephemeris
        'planets': 'de440.bsp',
        'satellites': {
            'mars': 'mar097.bsp',
            'jupiter': 'jup346.bsp',
            'saturn': 'sat454.bsp',
            'uranus': 'ura117.bsp',
            'neptune': 'nep104.bsp',
            'pluto': 'plu060.bsp',
        }
    },
}


naif_website: str = 'http://naif.jpl.nasa.gov/pub/naif/generic_kernels'
kernel_dir: str = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')
if not os.path.exists(kernel_dir):
    os.makedirs(kernel_dir)

def _fetch(site: str, subdir: str, filename: str, force: bool = False):
    url = '%s/%s/%s' %(site, subdir, filename)
    try:
        dest = os.path.join(kernel_dir, filename)
        if not force and os.path.exists(dest):
            return
        urllib.request.urlretrieve(url, dest)
    except Exception as e:
        print('No url: %s' % url)
        raise

def _update_filename(site: str, subdir: str, pattern: str):
    response = requests.get('%s/%s' % (site, subdir))
    soup = BeautifulSoup(response.text, 'html.parser')
    file_list = [node.get('href') for node in soup.find_all('a')
             if node.get('href') is not None and
             re.match(pattern, node.get('href'), re.IGNORECASE)]
    return sorted(file_list, reverse=True)[0]

def download(force: bool = False):
    print('Download NAIF kernels ...')
    if force:
        KERNELS['pck']['earth'] = _update_filename(naif_website, 'pck', r'earth_.*_combined\.bpc')
        KERNELS['pck']['moon'] = _update_filename(naif_website, 'pck', r'moon_.*\.bpc')

    _fetch(naif_website, 'lsk', KERNELS['lsk'], force)
    _fetch(naif_website, 'pck', KERNELS['tpc'], force)
    _fetch(naif_website, 'fk/planets', KERNELS['tf'], force)
    for _, val in KERNELS['pck'].items():
        _fetch(naif_website, 'pck', val, force)
    for key, val in KERNELS['spk'].items():
        if key == 'planets':
            _fetch(naif_website, 'spk/planets', val, force)
        else:
            for _, sub_val in val.items():
               _fetch(naif_website, 'spk/satellites', sub_val, force)
    print('... complete')

def _init_kernels(k_list):
    if not os.path.exists(kernel_dir) or \
            len(glob.glob(os.path.join(kernel_dir, '*.bpc'))) == 0:
        download()
    for k_id in k_list:
        filename = KERNELS
        for key in k_id.split('/'):
            filename = filename[key]
        spice.furnsh(os.path.join(kernel_dir, filename))

def _spherical_to_cartesian(theta: float, phi: float, R: float) -> list[float]:
    x = R * math.cos(phi) * math.cos(theta)
    y = R * math.cos(phi) * math.sin(theta)
    z = R * math.sin(phi)
    return [x, y, z]

def transform_coordinates(position: np.array, original: str, new: str, dt: datetime, init: bool = True) -> list[float]:
    k_list = ['lsk', 'tf', 'pck/earth']
    if init:
        _init_kernels(k_list)
    dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    et = spice.str2et(dt_str)
    converter = spice.pxform(original, new, et)
    if init:
        spice.kclear()
    return np.dot(converter, position).tolist()

def fixed_to_j2000(lat: float, lon: float, alt: float, dt: datetime) -> list[float]:
    k_list = ['lsk', 'tpc']
    _init_kernels(k_list)
    lat_rad = lat * np.pi / 180.
    lon_rad = lon * np.pi / 180.
    earth_body = 399
    _, radii = spice.bodvcd(earth_body, 'RADII', 3)
    equator = radii[0]
    polar = radii[2]
    f = (equator - polar) / equator
    epos = spice.georec(lon_rad, lat_rad, alt, equator, f)
    coords = transform_coordinates(epos, 'IAU_EARTH', 'J2000', dt, init=False)

    spice.kclear()
    return coords  # cartesian

def celestial_position(body: str, dt: datetime)-> list[float]:
    k_list = ['lsk', 'tpc']
    if body.upper() in PLANETS:
        k_list.append('spk/planets')
    elif body.upper() in SATELLITES_PLANET.keys():
        k_list.append('spk/satellites/' + SATELLITES_PLANET[body.upper()])
    _init_kernels(k_list)
    dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    et = spice.str2et(dt_str)
    position, _ = spice.spkpos(body.upper(), et, 'J2000', 'NONE', 'EARTH')
    spice.kclear()
    return position.tolist()

