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
from .abstract_query import AbsSpaceQuery, Position, CoordRefFrame, LatLonAlt, RaDec, Vector3

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

    def transform_coordinates(self, position: Position, original: str, new: str, dt: datetime) -> Position:
        orig_frame = self._validate_frame(original)
        new_frame = self._validate_frame(new)
        pos_arr = position.to_list()
        k_list = ['lsk', 'tf', 'pck/earth']
        self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        converter = spice.pxform(orig_frame.value, new_frame.value, et)
        self._clear_kernels()
        new_arr = np.dot(converter, pos_arr).tolist()
        if new_frame == CoordRefFrame.ITRF:
            return LatLonAlt(*new_arr)
        return RaDec(*new_arr)

    def celestial_position(self, body: str, dt: datetime)-> Vector3:
        if body.upper() not in NAIF_IDS:
            raise RuntimeError('Invalid celestial body: %s' % body)
        k_list = ['lsk', 'tpc']
        if body.upper() in PLANETS:
            k_list.append('spk/planets')
        elif body.upper() in SATELLITES_PLANET.keys():
            k_list.append('spk/planets')
            k_list.append('spk/satellites/' + SATELLITES_PLANET[body.upper()])
        self._init_kernels(k_list)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        et = spice.str2et(dt_str)
        try:
            position, _ = spice.spkpos(body.upper(), et, 'ECLIPJ2000', 'NONE', 'EARTH')
        except spice.exceptions.SpiceyError as err:
            raise RuntimeError("Kernels loaded: %s" % str(k_list)) from err
        self._clear_kernels()
        return self._spherical_to_cartesian(position)
