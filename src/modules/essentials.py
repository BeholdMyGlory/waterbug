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
import datetime
import io
import os
import subprocess
import sys
import traceback

import aniso8601
import dateutil.parser

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

    @waterbug.expose(access=waterbug.ADMIN)
    def disconnect(responder):
        responder.server.quit()

    @waterbug.expose(access=waterbug.ADMIN)
    def nick(responder, nick):
        responder.server.nick(nick)

    @waterbug.expose
    @asyncio.coroutine
    def alarm(responder, *args):
        try:
            line = responder.line.split("!", 1)
            if len(line) == 2:
                time, message = line
            else:
                time, message = line[0], "Alert!"
            time, message = time.strip(), message.strip()

            date = dateutil.parser.parse(time)
            now = datetime.datetime.now()
            if date <= now:
                responder("The given date is in the past")
            else:
                responder("Will run at {}".format(date.isoformat()))
                yield from asyncio.sleep((date - now).total_seconds())
                responder(message)
        except Exception:
            responder("Invalid date format")

    @waterbug.expose
    @asyncio.coroutine
    def timer(responder, *args):
        try:
            line = responder.line.split("!", 1)
            if len(line) == 2:
                time, message = line
            else:
                time, message = line[0], "Alert!"
            time, message = time.strip(), message.strip()

            delta = aniso8601.parse_duration(time)
            print(delta, delta.total_seconds())
            if delta.total_seconds() <= 0:
                responder("The given duration is negative")
            else:
                responder("Will run at {}".format((datetime.datetime.now() + delta).isoformat()))
                yield from asyncio.sleep(delta.total_seconds())
                responder(message)
        except Exception:
            responder("Invalid duration format")

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
                res = stdoutdata.decode('utf-8').strip().replace("\n", "; ")
                if len(res) == 0:
                    res = repr(None)
                responder("Result: " + res)
        except Exception:
            traceback.print_exc()
