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

__all__ = ['BANNED', 'STANDARD', 'TRUSTED',
           'ELEVATED', 'OP', 'ADMIN', 'Waterbug',
           'expose', 'trigger']

import asyncio
import collections
import functools
import glob
import inspect
import json
import logging
import os.path
import shelve
import sys
import traceback
import types

from . import network

BANNED = 0
STANDARD = 1
TRUSTED = 2
ELEVATED = 3
OP = 4
ADMIN = 5

class Waterbug:

    def __init__(self, *, loop=None):
        self.servers = {}
        self.commands = {}
        self.modules = []

        self.data = shelve.open("data.pck")

        with open("config.json") as config:
            self.config = json.load(config)

        # string -> integer constant conversion
        for server_config in self.config['servers'].values():
            if 'privileges' in server_config:
                for k, v in server_config['privileges'].items():
                    server_config['privileges'][k] = globals()[v]

        self.prefix = self.config['waterbug']['prefix']

        self.loop = loop or asyncio.get_event_loop()
        self._future = None

    @asyncio.coroutine
    def run(self):
        self._future = asyncio.Future()
        self.load_modules()
        yield from self.open_connections()
        yield from self._future
        self._future = None

    @asyncio.coroutine
    def open_connections(self):
        def _open_connection(server):
            def connection_closed(future):
                if server.reconnect:
                    logging.info("Reconnecting to %s", server.connection_name)
                    _open_connection(server)
                else:
                    logging.info("Removing %s from server list", server.connection_name)
                    del self.servers[server.connection_name]

            asyncio.async(server.connect(), loop=self.loop).add_done_callback(connection_closed)

        for name, config in self.config['servers'].items():
            server = network.Server(config['hostname'], config['port'],
                                    name, autojoin=config['autojoin'],
                                    access_list=config.get('privileges'),
                                    loop=self.loop)
            server.add_callback(self.on_privmsg, network.PRIVMSG)
            self.servers[name] = server

            _open_connection(server)

    def quit(self):
        for server in self.servers.values():
            server.quit()
        self.unload_modules()
        self._future.set_result(None)

    def unload_modules(self):
        for module in self.modules:
            if hasattr(module.commands, "unload"):
                if getattr(module.commands.unload, "trigger", False):
                    module.commands.unload()
        self.modules = []
        self.commands = {}

    def load_modules(self):
        self.unload_modules()

        for module_file in glob.glob("modules/*.py"):
            try:
                module_name = os.path.splitext(os.path.basename(module_file))[0]
                logging.info("Loading %s", module_name)
                module = types.ModuleType(module_name)
                module.STORAGE = Waterbug.ModuleStorage(module_name, self.data)
                module.CONFIG = self.config['modules'].get(module_name, {})

                with open(module_file) as f:
                    code = compile(f.read(), module_name, 'exec')
                    exec(code, module.__dict__, module.__dict__)
                self.modules.append(module)
            except Exception:
                traceback.print_exc()

        for module in self.modules:
            def add_commands(cls, command_dict):
                for name, value in inspect.getmembers(cls):
                    if getattr(value, "_exposed", False):
                        if inspect.isfunction(value):
                            command_dict[value.__name__] = value
                        else:
                            command_dict[name] = {}
                            add_commands(value, command_dict[name])

            module.commands = module.Commands
            add_commands(module.commands, self.commands)

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

    class Responder:

        def __init__(self, bot, server, sender, target, receiver, line):
            self.bot = bot
            self.server = server
            self.sender = sender
            self.target = target
            self.receiver = receiver
            self.line = line

        def __call__(self, msg, target=None, msgtype='PRIVMSG'):
            if msgtype == 'PRIVMSG':
                target = target or self.target
                self.server.msg(target, msg)
            elif msgtype == 'NOTICE':
                target = target or self.sender.username
                self.server.notice(target, msg)


    def get_command(self, args):
        commands = self.commands
        command_length = 0

        while (command_length < len(args)
                and isinstance(commands, collections.Mapping)
                and args[command_length] in commands):
            commands = commands[args[command_length]]
            command_length += 1

        if callable(commands):
            func = commands
        elif (isinstance(commands, collections.Mapping)
                and "_default" in commands
                and callable(commands["_default"])):
            func = commands["_default"]
        else:
            raise LookupError("Couldn't find a matching command")

        return func, args[:command_length], args[command_length:]

    def on_privmsg(self, server, event, sender, receiver, message):
        if receiver[0] in server.supported['CHANTYPES']:
            target = receiver
        else:
            target = sender
        if message.startswith(self.prefix):
            message = message[1:]

            try:
                func, _, args = self.get_command(message.split(" "))
            except LookupError:
                return

            if sender.access >= func.access:
                responder = Waterbug.Responder(self, server, sender, target,
                                               receiver, " ".join(args))
                try:
                    func(responder, *args)
                except TypeError:
                    responder("Wrong number of arguments")
                except BaseException:
                    traceback.print_exc()
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    exc = traceback.format_exception_only(exc_type, exc_value)
                    stack = traceback.format_tb(exc_traceback)
                    exception = "{}: {}".format(stack[-1], "".join(exc)).replace("\n", "")
                    server.msg(target, exception)
            else:
                server.msg(target, "You do not have access to this command")

def expose(*args, **kwargs):
    name = None
    access = STANDARD

    def decorator(target):
        target._exposed = True
        target.access = access
        if name is not None:
            target.__name__ = name
        if target.__doc__ is None:
            target.__doc__ = "No help available for this command"
        return target

    if len(args) == 1 and len(kwargs) == 0 and (callable(args[0]) or inspect.isclass(args[0])):
        return decorator(args[0])

    def get_args(name=None, access=STANDARD):
        return name, access

    name, access = get_args(*args, **kwargs)

    return decorator

def trigger(target):
    target.trigger = True
    return target

