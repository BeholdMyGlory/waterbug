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

import builtins
import io
import sys

import waterbug.waterbug as waterbug

class Commands:

    @waterbug.expose
    def echo(responder, *args):
        """Echoes back the written line"""
        responder(responder.line)

    @waterbug.expose(access=waterbug.ADMIN)
    def join(responder, channel):
        if len(channel) == 0:
            responder("You need to supply a channel to join")
        else:
            if channel[0] not in responder.server.supported["CHANTYPES"]:
                channel = responder.server.supported["CHANTYPES"][0] + channel
            responder("Joining {}".format(channel))
            responder.server.join(channel)

    @waterbug.expose(access=waterbug.ADMIN)
    def part(responder, channel=None):
        if channel is None:
            responder("Parting...")
            responder.server.part(responder.target)
        else:
            responder("Parting {}...".format(channel))
            responder.server.part(channel)

    @waterbug.expose(name="quit", access=waterbug.ADMIN)
    def quit_(responder):
        responder.bot.quit()

    @waterbug.expose(name="disconnect", access=waterbug.ADMIN)
    def disconnect(responder):
        responder.server.quit()

    @waterbug.expose(access=waterbug.ADMIN)
    def nick(responder, nick):
        responder.server.nick(nick)

