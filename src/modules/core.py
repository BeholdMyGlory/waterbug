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
import collections
import inspect
import io
import itertools
import sys

import waterbug

class Commands(waterbug.Commands):

    @waterbug.expose(name="eval", access=waterbug.ADMIN)
    def eval_(responder, *args):
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
    def reload(responder):
        """Reloads all modules"""
        responder.bot.load_modules()
        responder("Modules reloaded successfully")

    @waterbug.expose(name="help")
    def help_(responder, *args):
        """Displays help for the specified command"""

        try:
            command, command_list, _arg = responder.bot.get_command(args)
            if len(_arg) > 0:
                raise LookupError


            # WARNING: somewhat ugly workaround to deal with coroutines wrapping functions, making
            # the arg spec unavailable; if __wrapped__ is present, retreive the wrapped function
            while hasattr(command, '__wrapped__'):
                command = command.__wrapped__

            argspec = inspect.getfullargspec(command)


            if hasattr(command, "_argparser"):
                responder("{}{} {}: {}".format(responder.server.prefix, ' '.join(command_list),
                                               " ".join("[--{} {}]".format(k, v.__name__)
                                                        for k, v in argspec.annotations.items()),
                                               command.__doc__))
            else:
                cargs = argspec.args[1:] if argspec.defaults is None else argspec.args[1:-len(argspec.defaults)]
                cdefaults = zip(argspec.args[len(cargs) + 1:], () if argspec.defaults is None else argspec.defaults)
                signature = " ".join(x for x in [
                    " ".join("<{}>".format(arg) for arg in cargs),
                    " ".join("[{}={}]".format(arg, default) for arg, default in cdefaults),
                    "[{}...]".format(argspec.varargs) if argspec.varargs is not None else ''
                ] if len(x) > 0)

                responder("{}{}{}{}: {}".format(responder.server.prefix, " ".join(command_list),
                                                ' ' if signature else '', signature, command.__doc__))
        except LookupError:
            responder("No such command: '{}'".format(responder.line))

    @waterbug.expose
    def commands(responder):
        """Displays all available commands"""
        def flatten_dict(d):
            for k, v in d.items():
                if isinstance(v, collections.Mapping):
                    subcommands = "|".join(flatten_dict(v))
                    if '_default' in v and responder.sender.access >= v['_default'].access:
                        if len(subcommands) > 0:
                            yield k + " [" + subcommands + "]"
                        else:
                            yield k
                    elif len(subcommands) > 0:
                        yield k + " <" + subcommands + ">"
                    # output nothing if no accessible subcommands and _default not accessible
                elif k != '_default' and responder.sender.access >= v.access:
                    yield k

        commands = sorted(command for command in flatten_dict(responder.bot.commands))
        responder("Available commands: " + ', '.join(commands))



    @waterbug.expose
    @asyncio.coroutine
    def whoami(responder):
        """Displays your information such as username, hostname and access level"""
        responder.server.who(responder.sender.username)
        yield from responder.server.on("315")
        sender = responder.sender
        responder("You are {}!{}@{} ({}), {}, and you have access {}".format(
            sender.username, sender.ident, sender.hostname, sender.realname,
            "not logged in" if sender.account is None
                            else "logged in as {}".format(sender.account),
            sender.access))

    @waterbug.expose(access=waterbug.ADMIN)
    def access(responder, user, access_name):
        # TODO: fix this ugly line
        access_value = getattr(waterbug, access_name, None)
        if type(access_value) is not int:
            responder("Invalid access type")
            return

        responder.bot.privileges[user] = access_value
        responder("User {} is now {}".format(user, access_name))

