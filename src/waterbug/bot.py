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

__all__ = ['Waterbug', 'expose', 'trigger']

import argparse
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

import jsonschema

from . import network
from .constants import *

class Waterbug:

    def __init__(self, *, loop=None):
        self.servers = {}
        self.commands = {}
        self.modules = []
        self.queued_messages = {}
        self.async_operations = {}

        self.data = shelve.open("data.pck")

        with open("config.json") as config:
            self.config = json.load(config)

        jsonschema.validate(self.config, {
            "type": "object",
            "properties": {
                "servers": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "prefix": { "type": "string" },
                            "server": { "type": "string" },
                            "port": { "type": "integer" },
                            "username": { "type": "string" },
                            "ident": {
                                "type": "object",
                                "properties": {
                                    "user": { "type": "string" },
                                    "hostname": { "type": "string" },
                                    "servername": { "type": "string" },
                                    "realname": { "type": "string" },
                                },
                                "additionalProperties": False,
                                "required": ["user", "hostname", "servername", "realname"]
                            },
                            "autojoin": {
                                "type": "array",
                                "items": { "type": "string" }
                            },
                            "privileges": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "string",
                                    "enum": ["ADMIN", "OP", "ELEVATED",
                                             "TRUSTED", "STANDARD", "BANNED"]
                                }
                            },
                            "quit_msg": { "type": "string" },
                            "inencoding": { "type": "string" },
                            "outencoding": { "type": "string" }
                        },
                        "additionalProperties": False,
                        "required": ["prefix", "server", "port", "username"]
                    }
                },
                "modules": {
                    "additionalProperties": { "type": "object" }
                }
            },
            "additionalProperties": False,
            "required": ["servers"]
        })

        # string -> integer constant conversion
        for server_config in self.config['servers'].values():
            if 'privileges' in server_config:
                for k, v in server_config['privileges'].items():
                    server_config['privileges'][k] = globals()[v]

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
                    logging.info("Reconnecting to %s", server.name)
                    _open_connection(server)
                else:
                    logging.info("Removing %s from server list", server.name)
                    del self.servers[server.name]

            asyncio.async(server.connect(), loop=self.loop).add_done_callback(connection_closed)

        for name, config in self.config['servers'].items():
            server = network.Server(name=name, loop=self.loop, **config)
            self.servers[name] = server

            server.add_callback(self.on_privmsg, {"PRIVMSG"})
            server.add_callback(self.handle_queued_messages, {"JOIN", "PRIVMSG", "315"})

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
                module.LOGGER = logging.getLogger("module-" + module_name)
                module.BOT = self

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
                if target != self.sender.username:
                    msg = self.sender.username + ": " + msg
                self.server.msg(target, msg)
            elif msgtype == 'NOTICE':
                target = target or self.sender.username
                self.server.notice(target, msg)
            else:
                raise ValueError("Unknown msgtype {}".format(msgtype))


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
            target = sender.username
        if message.startswith(server.prefix):
            message = message[len(server.prefix):]

            try:
                func, _, args = self.get_command(message.split(" "))
            except LookupError:
                return

            if sender.access >= func.access:
                responder = Waterbug.Responder(self, server, sender, target,
                                               receiver, " ".join(args))

                @asyncio.coroutine
                def run_func():
                    try:
                        if hasattr(func, '_argparser'):
                            flags = func._argparser.parse_args(args)
                            res = func(responder, **vars(flags))
                        else:
                            res = func(responder, *args)
                        if asyncio.iscoroutine(res):
                            yield from res
                    except (TypeError, ValueError):
                        traceback.print_exc()
                        responder("Wrong number of arguments")
                    except Exception as e:
                        traceback.print_exc()
                        exception = ': '.join(traceback.format_exception(*sys.exc_info())[-2:])
                        exception = exception.replace('\n', '')
                        server.msg(target, exception)

                fut = asyncio.async(run_func(), loop=self.loop)
                self.async_operations[fut] = message
                def _remove_operation(_):
                    del self.async_operations[fut]
                fut.add_done_callback(_remove_operation)
            else:
                server.msg(target, "You do not have access to this command")

    def queue_message(self, connection, channel, hostname, message):
        self.queued_messages.setdefault((connection, channel, hostname), []).append(message)
        self.handle_queued_messages()

    def handle_queued_messages(self, *_args):
        to_remove = set()
        for (connection, channel, hostname), messages in self.queued_messages.items():
            if connection in self.servers and channel in self.servers[connection].channels:
                user = next((u for u in self.servers[connection].channels[channel].users.values()
                             if u.hostname == hostname), None)
                if user is not None:
                    for message in messages:
                        self.servers[connection].msg(channel, "{}: {}".format(
                            user.username, message))
                    to_remove.add((connection, channel, hostname))

        for i in to_remove:
            del self.queued_messages[i]



class ArgumentParser(argparse.ArgumentParser):

    def error(self, message):
        raise ValueError(message)

def expose(*args, **kwargs):
    name = None
    access = STANDARD
    flags = False

    def decorator(target):
        target._exposed = True
        target.access = access
        if name is not None:
            target.__name__ = name
        if target.__doc__ is None:
            target.__doc__ = "No help available for this command"

        if flags:
            argspec = inspect.getfullargspec(target)
            assert (len(argspec.args) == 1 and
                    len(argspec.kwonlydefaults) == len(argspec.annotations) and
                    all(key in argspec.annotations for key in argspec.kwonlydefaults))

            parser = ArgumentParser(add_help=False)
            for arg in argspec.kwonlydefaults:
                parser.add_argument('--' + arg, type=argspec.annotations[arg],
                                    default=argspec.kwonlydefaults[arg])

            target._argparser = parser

        return target

    if len(args) == 1 and len(kwargs) == 0 and (callable(args[0]) or inspect.isclass(args[0])):
        return decorator(args[0])

    def get_args(name=None, access=STANDARD, flags=False):
        return name, access, flags

    name, access, flags = get_args(*args, **kwargs)

    return decorator

def trigger(target):
    target.trigger = True
    return target
