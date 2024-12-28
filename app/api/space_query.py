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

try:
    from typing import Type, TypeVar
except ImportError:
    from typing_extensions import Type, TypeVar

from .spice_converter import SpiceQuery
from .astro_converter import AstroQuery
from .abstract_query import AbsSpaceQuery  # order is important


class SpaceQuery:
    _registered_impl: dict[str, Type[AbsSpaceQuery]] = {}

    @classmethod
    def get_impl(cls, name, *args, **kwargs) -> AbsSpaceQuery:
        return cls._registered_impl[name](*args, **kwargs)

    @classmethod
    def register_impl(cls, name: str, klass: Type[AbsSpaceQuery]):
        cls._registered_impl[name] = klass


SpaceQuery.register_impl('spice', SpiceQuery)
SpaceQuery.register_impl('astro', AstroQuery)
