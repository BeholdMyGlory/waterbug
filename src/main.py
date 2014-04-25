#   Waterbug, a modular IRC bot written using Python 3
#   Copyright (C) 2011  Arvid Fahlström Myrman
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import logging
import sys

import waterbug

def main(*argv):

    logging.basicConfig(format="%(asctime)s [%(name)s] %(message)s", datefmt="[%H:%M:%S]",
                        level=logging.INFO, stream=sys.stdout)

    bot = waterbug.Waterbug()
    asyncio.get_event_loop().run_until_complete(bot.run())

if __name__ == "__main__":
    main(*sys.argv)
