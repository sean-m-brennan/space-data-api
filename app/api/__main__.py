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

import sys
from typing import Optional

from .spice_converter import SpiceQuery


def main(argv: Optional[list[str]]=None) -> None:
    if argv is None:
        argv = sys.argv
    force = len(argv) > 1 and argv[1] == '--force'
    SpiceQuery().download(force=force)


if __name__ == '__main__':
    main()
