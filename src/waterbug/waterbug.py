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
import functools
import importlib
import inspect
import logging
import pkgutil
import shelve
import sys
import traceback
import types

import waterbug.modules
import waterbug.network
import waterbug.util

BANNED = 0
STANDARD = 1
TRUSTED = 2
ELEVATED = 3
OP = 4
ADMIN = 5

class Waterbug:

    def __init__(self, prefix='%'):
        self.servers = {}
        self.commands = {}
        self.modules = []
        self.prefix = prefix

        self.data = shelve.open("data.pck")

        self.config = {
            "waterbug": {
                "prefix": "%"
            },
            "servers": {
                "FreeNode": {
                    "hostname": "chat.freenode.net",
                    "port": 6667,
                    "autojoin": ["##FireFly"],
                    "privileges": {
                        "unaffiliated/beholdmyglory": ADMIN
                    }
                }
            },
            "modules": {
                "anidb": {
                    "server": "api.anidb.net",
                    "port": 9001,
                    "protoversion": 1,
                    "clientname": "eldishttp",
                    "clientversion": 1
                }
            }
        }

        self.privileges = {
            "unaffiliated/beholdmyglory": ADMIN
        }

    @asyncio.coroutine
    def run(self):
        self.load_modules()
        yield from self.open_connections()

    @asyncio.coroutine
    def open_connections(self):

        for name, config in self.config['servers'].items():
            server = waterbug.network.Server(config['hostname'], config['port'], name, self)
            self.servers[name] = server

            logging.info("Connecting to %s (%s)", name, server.server)

            yield from server.connect()

            try:
                for channel in self.config['servers'][name]['autojoin']:
                    server.join(channel)
            except KeyError:
                pass # no channels to autojoin

    def unload_modules(self):
        for module in self.modules:
            if hasattr(module.commands, "unload"):
                if getattr(module.commands.unload, "trigger", False):
                    module.commands.unload()
        self.modules = []
        self.commands = {}

    def load_modules(self):
        self.unload_modules()

        for _, module_name, _ in pkgutil.iter_modules(waterbug.modules.__path__):
            try:
                logging.info("Loading %s", module_name)
                module = types.ModuleType(module_name)
                with open('waterbug/modules/{}.py'.format(module_name)) as f:
                    code = compile(f.read(), module_name, 'exec')
                    exec(code, module.__dict__, module.__dict__)
                self.modules.append(module)
            except Exception:
                traceback.print_exc()

        for module in self.modules:
            try:

                module_data = Waterbug.ModuleStorage(module.__name__, self.data)

                def add_commands(cobj, clist):
                    cobj.bot = self
                    cobj.data = module_data
                    if hasattr(cobj, "init") and getattr(cobj.init, "trigger", False):
                        cobj.init()
                    for name, value in inspect.getmembers(cobj):
                        if getattr(value, "exposed", False):
                            if callable(value):
                                clist[value.__name__] = value
                            else:
                                clist[name] = {}
                                add_commands(value, clist[name])


                module.commands = module.Commands()
                add_commands(module.commands, self.commands)

            except BaseException:
                traceback.print_exc()

    class ModuleStorage:

        def __init__(self, name, data):
            self.name = name
            if name not in data:
                data[name] = {}
            self.data = data[name]
            self._data = data

        def sync(self):
            self._data[self.name] = self.data
            self._data.sync()

        def get_data(self):
            return self.data


    def on_privmsg(self, server, sender, receiver, message):
        if receiver[0] in server.supported['CHANTYPES']:
            target = receiver
        else:
            target = sender
        if message.startswith(self.prefix):
            message = message[1:]
            command, args = waterbug.util.reduce_until(lambda x, y: x[y], message.split(" "), self.commands,
                                                       lambda x, y: type(x) is dict and y in x)

            if callable(command):
                func = command
            elif type(command) is dict and "_default" in command and callable(command["_default"]):
                func = command["_default"]
            else:
                return

            if sender.access >= func.access:
                try:
                    func({"command": command, "sender": sender, "target": target,
                          "receiver": receiver, "line": " ".join(args)}, server, *args)
                except BaseException:
                    traceback.print_exc()
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    exc = traceback.format_exception_only(exc_type, exc_value)
                    stack = traceback.format_tb(exc_traceback)
                    exception = "{}: {}".format(stack[-1], "".join(exc)).replace("\n", "")
                    server.msg(target, exception)
            else:
                server.msg(target, "You do not have access to this command")

def expose(name=None, access=STANDARD):
    def decorator(target):
        target.exposed = True
        target.access = access
        if name is not None:
            target.__name__ = name
        if target.__doc__ is None:
            target.__doc__ = "No help available for this command"
        return target
    return decorator

def trigger(target):
    target.trigger = True
    return target

