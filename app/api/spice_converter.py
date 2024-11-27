#!/usr/bin/env python
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

import os
import glob
import math
import re
import tempfile
from datetime import datetime
import urllib.request

import requests
from bs4 import BeautifulSoup
import numpy as np
import spiceypy as spice

from .naif_ids import PLANETS, SATELLITES_PLANET


JGM3Re: float = 6378.137
NAIF_WEBSITE: str = 'http://naif.jpl.nasa.gov/pub/naif/generic_kernels'
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

class SpiceQuery:
    def __init__(self, jit: bool = False):
        self.just_in_time = jit
        self.kernel_dir = tempfile.gettempdir()
        if not jit:
            self.kernel_dir = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')
        self.kernels_loaded = []

    def _clear_kernels(self):
        if not self.just_in_time:
            spice.kclear()
            self.kernels_loaded = []

    @staticmethod
    def _kernel_location(k_name):
        if k_name == KERNELS['lsk']:
            return 'lsk'
        if k_name == KERNELS['tpc']:
            return 'pck'
        if k_name == KERNELS['tf']:
            return 'fk/planets'
        for _, val in KERNELS['pck'].items():
            if k_name == val:
                return 'pck'
        for key, val in KERNELS['spk'].items():
            if k_name == val:
                if key == 'planets':
                    return 'spk/planets'
                else:
                    return 'spk/satellites'

    def _fetch(self, site: str, filename: str, force: bool = False):
        if not os.path.exists(self.kernel_dir):
            os.makedirs(self.kernel_dir)
        subdir = self._kernel_location(filename)
        url = '%s/%s/%s' %(site, subdir, filename)
        try:
            dest = os.path.join(self.kernel_dir, filename)
            if not force and os.path.exists(dest):
                return
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print('No url: %s' % url)
            raise

    @staticmethod
    def _update_filename(site: str, subdir: str, pattern: str):
        response = requests.get('%s/%s' % (site, subdir))
        soup = BeautifulSoup(response.text, 'html.parser')
        file_list = [node.get('href') for node in soup.find_all('a')
                     if node.get('href') is not None and
                         re.match(pattern, node.get('href'), re.IGNORECASE)]
        return sorted(file_list, reverse=True)[0]

    def download(self, force: bool = False):
        print('Download NAIF kernels ...')
        if force:
            KERNELS['pck']['earth'] = self._update_filename(NAIF_WEBSITE, 'pck', r'earth_.*_combined\.bpc')
            KERNELS['pck']['moon'] = self._update_filename(NAIF_WEBSITE, 'pck', r'moon_.*\.bpc')

        self._fetch(NAIF_WEBSITE, KERNELS['lsk'], force)
        self._fetch(NAIF_WEBSITE, KERNELS['tpc'], force)
        self._fetch(NAIF_WEBSITE, KERNELS['tf'], force)
        for _, val in KERNELS['pck'].items():
            self._fetch(NAIF_WEBSITE, val, force)
        for key, val in KERNELS['spk'].items():
            if key == 'planets':
                self._fetch(NAIF_WEBSITE, val, force)
            else:
                for _, sub_val in val.items():
                    self._fetch(NAIF_WEBSITE, sub_val, force)
        print('... complete')

    def _init_kernels(self, k_list: list[str]):
        if self.just_in_time:
            for k_id in k_list:
                filename = KERNELS
                for key in k_id.split('/'):
                    filename = filename[key]
                if filename in self.kernels_loaded:
                    continue
                # not using async because space is the tighter constraint
                self._fetch(NAIF_WEBSITE, filename)
                spice.furnsh(os.path.join(self.kernel_dir, filename))
                self.kernels_loaded.append(filename)
                os.remove(os.path.join(self.kernel_dir, filename))
        else:
            if not os.path.exists(self.kernel_dir) or \
                    len(glob.glob(os.path.join(self.kernel_dir, '*.bpc'))) == 0:
                self.download()
            for k_id in k_list:
                filename = KERNELS
                for key in k_id.split('/'):
                    filename = filename[key]
                spice.furnsh(os.path.join(self.kernel_dir, filename))

    @staticmethod
    def _spherical_to_cartesian(theta: float, phi: float, R: float) -> list[float]:
        x = R * math.cos(phi) * math.cos(theta)
        y = R * math.cos(phi) * math.sin(theta)
        z = R * math.sin(phi)
        return [x, y, z]

    def transform_coordinates(self, position: np.array, original: str, new: str, dt: datetime, init: bool = True) -> list[float]:
        k_list = ['lsk', 'tf', 'pck/earth']
        if init:
            self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        converter = spice.pxform(original, new, et)
        if init:
            self._clear_kernels()
        return np.dot(converter, position).tolist()

    def fixed_to_j2000(self, lat: float, lon: float, alt: float, dt: datetime) -> list[float]:
        k_list = ['lsk', 'tpc']
        self._init_kernels(k_list)
        lat_rad = lat * np.pi / 180.
        lon_rad = lon * np.pi / 180.
        earth_body = 399
        _, radii = spice.bodvcd(earth_body, 'RADII', 3)
        equator = float(radii[0])
        polar = float(radii[2])
        f = (equator - polar) / equator
        epos = spice.georec(lon_rad, lat_rad, alt, equator, f)
        coords = self.transform_coordinates(epos, 'IAU_EARTH', 'J2000', dt, init=False)
        self._clear_kernels()
        return coords  # cartesian

    def celestial_position(self, body: str, dt: datetime)-> list[float]:
        k_list = ['lsk', 'tpc']
        if body.upper() in PLANETS:
            k_list.append('spk/planets')
        elif body.upper() in SATELLITES_PLANET.keys():
            k_list.append('spk/satellites/' + SATELLITES_PLANET[body.upper()])
        self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        position, _ = spice.spkpos(body.upper(), et, 'J2000', 'NONE', 'EARTH')
        self._clear_kernels()
        return position.tolist()

