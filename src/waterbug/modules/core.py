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

import collections
import io
import itertools
import sys

import waterbug.waterbug as waterbug

class Commands:

    @waterbug.expose(name="eval", access=waterbug.ADMIN)
    def eval_(self, responder, *args):
        """Evaluates a Python expression in an unrestricted context"""
        result = io.StringIO()
        # NOTE: Reassigning stdout is not threadsafe.
        #       Shouldn't pose a problem when running on a single event loop.
        old_stdout = sys.stdout
        sys.stdout = result
        exec(compile(responder.line + "\n", "<input>", "single"))
        sys.stdout = old_stdout
        result = result.getvalue().strip().replace("\n", "; ")
        if len(result) == 0:
            result = repr(None)
        responder("Result: " + result)

    @waterbug.expose(access=waterbug.ADMIN)
    def reload(self, responder, *args):
        """Reloads all modules"""
        responder.bot.load_modules()
        responder("Modules reloaded successfully")

    @waterbug.expose(name="help")
    def help_(self, responder, *args):
        """Displays help for the specified command"""

        try:
            command, _ = responder.bot.get_command(args)
            responder(command.__doc__)
        except LookupError:
            responder("No such command: '{}'".format(responder.line))

    @waterbug.expose()
    def commands(self, responder, *args):
        """Displays all available commands"""
        def flatten_dict(d):
            queue = collections.deque([('', d)])
            while len(queue) > 0:
                prefix, d = queue.popleft()
                for k, v in d.items():
                    if isinstance(v, collections.Mapping):
                        if '_default' in v:
                            yield prefix + k, v['_default']
                        queue.append((prefix + (' ' if prefix else '') + k, v))
                    elif k != '_default':
                        yield prefix + k, v

        commands = sorted(command for command, function in flatten_dict(responder.bot.commands)
                                  if responder.sender.access >= function.access)
        responder("Available commands: " + ', '.join(commands))

    @waterbug.expose()
    def whoami(self, responder, *args):
        """Displays your information such as username, hostname and access level"""
        responder("You are {}!{}@{}, and you have access {}".format(
            responder.sender.username, responder.sender.ident,
            responder.sender.hostname, responder.sender.access))

    @waterbug.expose(access=waterbug.ADMIN)
    def access(self, responder, *args):
        try:
            user, access_name = args
        except ValueError:
            responder("Invalid number of parameters")
            return

        # TODO: fix this ugly line
        access_value = getattr(waterbug, access_name, None)
        if type(access_value) is not int:
            responder("Invalid access type")
            return

        responder.bot.privileges[user] = access_value
        responder("User {} is now {}".format(user, access_name))

