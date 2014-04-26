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
import builtins
import io
import os
import subprocess
import sys
import traceback

import waterbug

class Commands:

    @waterbug.expose
    def echo(responder, *args):
        """Echoes back the written line"""
        responder(responder.line)

    @waterbug.expose(access=waterbug.ADMIN)
    def join(responder, channel):
        """Joins a channel on the same network"""
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

    @waterbug.expose
    @asyncio.coroutine
    def py(responder, *args):
        try:
            proc = yield from asyncio.create_subprocess_exec(
                '/usr/bin/python2', 'pypy/sandbox/pypy_interact.py',
                '--tmp=../pypy-sandbox',
                '--timeout=1', '--heapsize=100m', 'pypy/goal/pypy-c',
                '/tmp/read_code_from_stdin.py',
                cwd='modules/pypy2', env={'PYTHONPATH': '.'},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            stdoutdata, stderrdata = yield from proc.communicate(responder.line.encode())

            if stderrdata.strip().split(b'\n')[-1] == b'[Subprocess killed by SIGTERM]':
                responder("Timed out!")
            else:
                res = stdoutdata.decode('utf-8').strip()
                if len(res) == 0:
                    res = 'None'
                responder("Result: " + res)
        except Exception:
            traceback.print_exc()
