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

    def __init__(self):
        self.g_context = {"__builtins__": {x: getattr(builtins, x)
                                           for x in ["abs", "all", "any", "ascii", "bin",
                                                     "bool", "bytearray", "bytes", "callable",
                                                     "chr", "classmethod", "complex",
                                                     "delattr", "dict", "dir", "divmod",
                                                     "enumerate", "filter", "float",
                                                     "format", "frozenset", "getattr",
                                                     "hasattr", "hash", "help",
                                                     "hex", "id", "int", "isinstance",
                                                     "issubclass", "iter", "len", "list",
                                                     "locals", "map", "max", "memoryview",
                                                     "min", "next", "object", "oct",
                                                     "ord", "pow", "property", "range",
                                                     "repr", "reversed", "round", "set",
                                                     "setattr", "slice", "sorted",
                                                     "staticmethod", "str", "sum", "super",
                                                     "tuple", "type", "vars", "zip",
                                                     "__build_class__"]}}
        def _import(*args):
            if args[0] in ["math"]:
                return __import__(*args)
            else:
                raise ImportError("No module named " + args[0])
        self.g_context['__builtins__']['__import__'] = _import
        self.g_context['__name__'] = "__irc__"
        self.l_context = {}

    @waterbug.expose()
    def echo(self, data, server, *args):
        """Echoes back the written line"""
        server.msg(data["target"], data["line"])

    @waterbug.expose(access=waterbug.ADMIN)
    def join(self, data, server, channel=None, *args):
        if channel is None or len(channel) < 1:
            server.msg(data["target"], "You need to supply a channel to join")
        else:
            if channel[0] not in server.supported["CHANTYPES"]:
                channel = server.supported["CHANTYPES"][0] + channel
            server.msg(data["target"], "Joining {}".format(channel))
            server.join(channel)

    @waterbug.expose(access=waterbug.ADMIN)
    def part(self, data, server, channel=None, *args):
        if channel is None:
            server.msg(data["target"], "Parting...")
            server.part(data["target"])
        else:
            server.msg(data["target"], "Parting {}...".format(channel))
            server.part(channel)

    @waterbug.expose(name="quit", access=waterbug.ADMIN)
    def quit_(self, data, server, *args):
        self.bot.quit()

    @waterbug.expose(name="disconnect", access=waterbug.ADMIN)
    def disconnect(self, data, server, *args):
        server.quit()

    @waterbug.expose(access=waterbug.ADMIN)
    def nick(self, data, server, nick=None, *args):
        if nick is None:
            server.msg(data["target"], "You need to supply a username")
        else:
            server.nick(nick)

    #@waterbug.expose()
    def py(self, data, server, *args):
        result = io.StringIO()
        #TODO: Reassigning stdout is not threadsafe!
        old_stdout = sys.stdout
        sys.stdout = result
        exec(compile(data['line'] + "\n", "<input>", "single"), self.g_context, self.l_context)
        sys.stdout = old_stdout
        result = result.getvalue().strip().replace("\n", "; ")
        if len(result) == 0:
            result = repr(None)
        server.msg(data["target"], "Result: " + result)
