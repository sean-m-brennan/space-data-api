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
import re
import tempfile
from datetime import datetime
import urllib.request

import requests
from bs4 import BeautifulSoup
import numpy as np
import spiceypy as spice

from .naif_ids import PLANETS, SATELLITES_PLANET, NAIF_IDS
from .abstract_query import AbsSpaceQuery, Position, CoordRefFrame, LatLonAlt, RaDec, Vector3, u

JGM3Re: float = 6378.137
NAIF_WEBSITE: str = 'http://naif.jpl.nasa.gov/pub/naif/generic_kernels'

#TODO fetch structure dynamically (plus file dates)
KERNELS: dict[str, str | dict[str, str | dict[str, str]]] = {
    'lsk': 'latest_leapseconds.tls',  # time
    'tpc': 'pck00010.tpc',  # orientation
    'tf': 'earth_assoc_itrf93.tf',  # reference frame
    'pck': { # planet constants
        'earth': 'earth_1962_240827_2124_combined.bpc',
        'moon': 'moon_pa_de440_200625.bpc',
        #'masses': 'de-403-masses.tpc'
    },
    'spk': {  # planetary ephemeris
        'planets': ['de440.bsp', 'de430.bsp'],
        'satellites': {
            'mars': 'mar097.bsp',
            'jupiter': 'jup346.bsp',
            'saturn': 'sat454.bsp',
            'uranus': 'ura117.bsp',
            'neptune': 'nep104.bsp',
            'pluto': 'plu060.bsp',
        },
        'asteroids': 'codes_300ast_20100725.bsp'
    },
}

class SpiceQuery(AbsSpaceQuery):
    default_kernels = ['tpc', 'lsk', 'spk/asteroids']
    kernel_cache = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'kernels')

    def __init__(self, jit: bool = False):
        super().__init__()
        self.just_in_time = jit
        self.kernel_dir = tempfile.gettempdir()
        if not jit:
            self.kernel_dir = self.kernel_cache
        self.kernels_loaded = []
        # FIXME do download here

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
            if key == 'planets' and k_name in val:
                return 'spk/planets'
            elif key == 'asteroids' and k_name == val:
                return 'spk/asteroids'
            elif key == 'satellites' and k_name in val.values():
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
            # TODO only download if newer
            urllib.request.urlretrieve(url, dest)
        except Exception as _e:
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
                for sub in val:
                    self._fetch(NAIF_WEBSITE, sub, force)
            elif key == 'asteroids':
                self._fetch(NAIF_WEBSITE, val, force)
            else:
                for _, sub_val in val.items():
                    self._fetch(NAIF_WEBSITE, sub_val, force)
        print('... complete')

    @staticmethod
    def _resolve_kernels(k_id: str) -> list[str]:
        """Resolve a slash-path key into the kernel filename(s) it points at.

        Some entries (e.g. 'spk/planets') map to a *list* of kernels rather than a
        single filename; always return a list so callers can furnish each one.
        """
        node = KERNELS
        for key in k_id.split('/'):
            node = node[key]
        return node if isinstance(node, list) else [node]

    def _init_kernels(self, k_list: list[str]):
        if self.just_in_time:
            for k_id in k_list:
                for filename in self._resolve_kernels(k_id):
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
                for filename in self._resolve_kernels(k_id):
                    spice.furnsh(os.path.join(self.kernel_dir, filename))

    def transform_coordinates(self, position: Position, original: str, new: str, dt: datetime) -> Position:
        orig_frame = self._validate_frame(original)
        new_frame = self._validate_frame(new)
        # The frame change is a pure rotation of a CARTESIAN vector. Reduce any polar input
        # to cartesian first, rotate, then return in the SAME form as the input (a polar
        # input yields a polar result in the representation natural to the target frame:
        # terrestrial -> LatLonAlt, celestial -> RaDec).
        is_polar = not isinstance(position, Vector3)
        cart = self._spherical_to_cartesian(position) if is_polar else position
        unit = cart.z.units
        pos_arr = [cart.x.magnitude, cart.y.magnitude, cart.z.magnitude]
        k_list = ['lsk', 'tf', 'pck/earth']
        self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        converter = spice.pxform(orig_frame.value, new_frame.value, et)
        self._clear_kernels()
        new_arr = np.dot(converter, pos_arr).tolist()
        rotated = Vector3(new_arr[0] * unit, new_arr[1] * unit, new_arr[2] * unit)
        if not is_polar:
            return rotated
        klass = LatLonAlt if new_frame == CoordRefFrame.ITRF else RaDec
        return self._cartesian_to_polar(rotated, klass)

    def celestial_position(self, body: str, dt: datetime)-> Vector3:
        if body.upper() not in NAIF_IDS:
            raise RuntimeError('Invalid celestial body: %s' % body)
        k_list = ['lsk', 'tpc']
        body_u = body.upper()
        satellites = KERNELS['spk']['satellites']  # planet name (lowercase) -> kernel
        if body_u in PLANETS:
            k_list.append('spk/planets')
            # The planet *body* center (e.g. Mars 499) is provided by the per-planet
            # satellite SPK, not the DE ephemeris (which supplies system barycenters).
            if body.lower() in satellites:
                k_list.append('spk/satellites/' + body.lower())
        elif body_u in SATELLITES_PLANET:
            k_list.append('spk/planets')
            # KERNELS['spk']['satellites'] is keyed by the lowercase planet name.
            k_list.append('spk/satellites/' + SATELLITES_PLANET[body_u].lower())
        elif body_u == 'MOON':
            k_list.append('spk/planets')  # the Moon (301) is provided by the DE ephemeris
        self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        try:
            position, _ = spice.spkpos(body.upper(), et, 'ECLIPJ2000', 'NONE', 'EARTH')
        except spice.exceptions.SpiceyError as err:
            raise RuntimeError("Kernels loaded: %s" % str(k_list)) from err
        self._clear_kernels()
        # spkpos already returns a cartesian ECLIPJ2000 vector in km (geocentric);
        # return it directly rather than treating it as a polar coordinate.
        return Vector3(float(position[0]) * u.km, float(position[1]) * u.km, float(position[2]) * u.km)
