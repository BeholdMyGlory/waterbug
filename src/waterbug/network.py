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

__all__ = ['Server', 'Channel', 'User', 'fetch_url']

import asyncio
import collections
import datetime
import itertools
import logging
import socket
import time
import traceback

import aiohttp

from .constants import *


class Server:

    def __init__(self, prefix, server, port, name, username,
                 quit_msg=None, ident=None,
                 autojoin=[], privileges=None, inencoding="irc", outencoding="utf8",
                 reconnect=True, max_reconnects=5, connect_timeout=30,
                 keepalive_interval=60, throttle=1, *, loop=None):
        self.loop = loop or asyncio.get_event_loop()

        self.prefix = prefix
        self.channels = CaseInsensitiveDict()
        self.users = CaseInsensitiveDict()
        self.inencoding = inencoding
        self.outencoding = outencoding
        self.name = name
        self.username = username
        self.original_username = username
        self.ident = ident or {
            "user": "".join(c for c in self.username.lower() if 'a' <= c <= 'z'),
            "hostname": "-",
            "servername": "-",
            "realname": self.username
        }
        self.quit_msg = quit_msg or self.username + " quitting..."
        self.autojoin = autojoin
        self.access_list = privileges or {}

        self.supported = {}

        self.receiver = Server.MessageReceiver(self)
        self.callbacks = collections.defaultdict(set)

        self.server = server
        self.port = port
        self.host = None
        self.connected = False
        self.welcomed = False

        self.reconnect = reconnect
        self.max_reconnects = max_reconnects
        self.connect_timeout = connect_timeout
        self.keepalive_interval = keepalive_interval
        self.throttle = throttle
        self.message_queue = asyncio.Queue()
        self.writer_task = None

        self.logger = logging.getLogger(name)

    @asyncio.coroutine
    def on(self, *messagetypes):
        future = asyncio.Future()
        key = self.add_callback(lambda *args: future.set_result(args), messagetypes)
        try:
            return (yield from future)
        finally:
            self.remove_callback(key)

    def add_callback(self, callback, flags):
        keys = set()
        obj = object()
        flags = frozenset(flags)
        for flag in flags:
            key = obj, callback, flag, flags
            keys.add(key)
            self.callbacks[flag].add(key)
        return keys

    def remove_callback(self, keys):
        for key in keys:
            self.callbacks[key[2]].remove(key)

    def run_callbacks(self, flag, *parameters):
        for _, callback, _, _ in self.callbacks[flag]:
            try:
                callback(self, flag, *parameters)
            except Exception:
                self.logger.exception("Exception while processing callback '%s' with parameters %s",
                                      callback.__name__, parameters)

    def reset_connection(self):
        self.channels = CaseInsensitiveDict()
        self.users = CaseInsensitiveDict()
        self.supported = {}
        self.connected = False
        self.welcomed = False
        self.writer.close()
        if self.writer_task is not None:
            self.writer_task.cancel()
            self.writer_task = None
        self.message_queue = asyncio.Queue()
        self._keepalive_handler.cancel()

    @asyncio.coroutine
    def connect(self):
        self.logger.info("Connecting to %s (%s:%s)", self.name, self.server, self.port)

        for attempt in range(self.max_reconnects):
            if attempt > 0:
                self.logger.warning("Connection attempt timed out, retrying...")

            try:
                self.reader, self.writer = yield from asyncio.wait_for(
                    asyncio.open_connection(self.server, self.port, loop=self.loop),
                    self.connect_timeout)
                self.connected = True
                break
            except asyncio.TimeoutError:
                pass # continue
        else:
            # connection attempt failed
            self.logger.warning("Maximum number of connection attempts exceeded, giving up...")
            self.reconnect = False
            return

        self.writer_task = asyncio.async(self.handle_write(), loop=self.loop)

        self.nick(self.username)
        self.user(self.ident)

        yield from self.read()

    @asyncio.coroutine
    def read(self):
        while True:
            try:
                data = yield from asyncio.wait_for(self.reader.readline(),
                                                   self.keepalive_interval * 3)
            except asyncio.TimeoutError:
                self.logger.warning("Read timed out, connection assumed lost")
                break

            if data[-2:] != b'\r\n':
                self.logger.warning("Got partial read, connection assumed lost")
                break
            else:
                data = data[:-2]

            if self.inencoding == "irc":
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("latin", "replace")
            else:
                text = data.decode(self.inencoding)

            self.message_last_received = time.time()

            self.logger.debug("<< %s", text)

            if text.startswith(":"):
                username, msgtype, *parameters = text[1:].split(' ') #remove starting :
                try:
                    username, host = username.split('!', 2)
                except ValueError:
                    host = None # username keeps its original value

                ident = None
                access = STANDARD
                if host is not None:
                    ident, host = host.split("@", 2)
                    access = self.access_list.get(host, access)

                if username in self.users:
                    user = self.users[username]
                    if host is not None:
                        user.hostname = host
                    if ident is not None:
                        user.ident = ident
                    user.access = access
                else:
                    user = User(username, self, access, ident, host)

                for i, v in enumerate(parameters):
                    if v.startswith(":"):
                        #remove the : and join together all succeeding parameters
                        #into one long parameter
                        parameters[i:] = [' '.join([v[1:]] + parameters[i + 1:])]
                        break

                try:
                    could_parse_message = self.receiver(msgtype, user, *parameters)
                except Exception:
                    self.logger.exception("Exception while parsing message: %s", text)

                if could_parse_message:
                    self.run_callbacks(msgtype, user, *parameters)
            else:
                self.logger.info("Server sent: %s", text)
                if text.startswith("PING"):
                    self.write("PONG " + text.split(' ')[1])

        self.logger.warning("Aborted reading from server")
        self.reset_connection()

    def on_welcome(self, host):
        self.host = host
        self.welcomed = True

        # perform autojoins
        for channel in self.autojoin:
            self.join(channel)

        self._keepalive_handler = self.loop.call_later(self.keepalive_interval, self.keepalive)

    def keepalive(self):
        if self.host is not None:
            self.write("PING :{}".format(self.host), log=False)

        self._keepalive_handler = self.loop.call_later(self.keepalive_interval, self.keepalive)

    def msg(self, target, message):
        self.write("PRIVMSG {} :{}".format(target, message))

    def notice(self, target, message):
        self.write("NOTICE {} :{}".format(target, message))

    def join(self, channel):
        self.write("JOIN {}".format(channel))

    def part(self, channel):
        self.write("PART {}".format(channel))

    def nick(self, nick):
        self.write("NICK :{}".format(nick))

    def user(self, ident):
        self.write("USER {} {} {} :{}".format(ident["user"], ident["hostname"],
                                              ident["servername"], ident["realname"]))

    def quit(self):
        self.write("QUIT :{}".format(self.quit_msg))
        self.writer.close()
        self.reconnect = False

    def who(self, mask, extended=True):
        if extended:
            self.write("WHO {} %uhnfar".format(mask))
        else:
            self.write("WHO {}".format(mask))

    def write(self, line, log=True):
        # replace control characters
        line = "".join("[{}]".format(ord(x)) if ord(x) < 0x20 else x for x in line)

        maxlength = self.supported.get('TOPICLEN', 300)
        if len(line) > maxlength:
            line = "{} {}".format(line[:maxlength], "<...>")

        self.message_queue.put_nowait((line, log))

    @asyncio.coroutine
    def handle_write(self):
        try:
            while True:
                line, log = yield from self.message_queue.get()
                if log:
                    self.logger.info(">> %s", line)
                self.writer.write(line.encode(self.outencoding) + b'\r\n')
                yield from asyncio.sleep(self.throttle)
        except asyncio.CancelledError:
            pass

    class MessageReceiver:

        def __init__(self, server):
            self.server = server

        def PRIVMSG(self, sender, target, message):
            self.server.logger.info("<%s to %s> %s", sender, target, message)

        def NOTICE(self, sender, target, message):
            self.server.logger.info("[NOTICE] <%s to %s> %s", sender, target, message)

        def JOIN(self, sender, channel):
            self.server.logger.info("%s joined channel %s", sender, channel)

            if sender is self.server.ownuser:
                self.server.channels[channel] = Channel(channel)
                self.server.who(channel)
            else:
                self.server.who(sender.username)

            sender.add_channel(self.server.channels[channel])

        def PART(self, sender, channel, message=""):
            self.server.logger.info("%s parted from channel %s with message %s", sender, channel, message)

            sender.remove_channel(self.server.channels[channel])

        def KICK(self, sender, channel, kickee, message=""):
            self.server.logger.info("%s kicked %s from channel %s with message %s", sender, kickee, channel, message)
            self.PART(self.server.users[kickee], channel, message)

        def QUIT(self, sender, message=""):
            self.server.logger.info("User %s quit with message %s", sender, message)

            for channel in sender.knownchannels.values():
                del channel.users[sender.username]

            del self.server.users[sender.username]

        def NICK(self, sender, message):
            self.server.logger.info("User %s changed nick to %s", sender, message)

            sender.rename(message)

        def TOPIC(self, sender, channel, topic):
            self.server.logger.info("User %s changed the topic of %s to %s", sender, channel, topic)

            channel = self.server.channels[channel]
            channel.topic = topic
            channel.topicchanger = "{}!{}@{}".format(sender.username, sender.ident, sender.hostname)
            channel.topicchanged = datetime.datetime.now()

        def PONG(self, sender, host, message):
            #self.server.logger.info("[PONG] %s", message)
            pass

        def _001(self, sender, user, message):
            self.server.logger.info("[Welcome] %s", message)
            self.server.ownuser = User(user, self.server)
            self.server.users[user] = self.server.ownuser

            self.server.on_welcome(sender)

        def _002(self, sender, user, message):
            self.server.logger.info("[Host] %s", message)

        def _003(self, sender, user, message):
            self.server.logger.info("[Created] %s", message)

        def _004(self, sender, user, host, version, usermodes, chanmodes, *supported):
            self.server.logger.info("[My Info] I am %s running %s. User modes: %s. Channel modes: %s",
                         host, version, usermodes, chanmodes)

        def _005(self, sender, user, *message):
            self.server.logger.info("[Supported] %s", message)
            for i in itertools.islice(message, len(message)-1):
                a = i.split("=", 2)
                if len(a) == 2:
                    try:
                        a[1] = int(a[1])
                    except ValueError:
                        try:
                            a[1] = float(a[1])
                        except ValueError:
                            pass
                    self.server.supported[a[0]] = a[1]
                else:
                    self.server.supported[a[0]] = True

        def _250(self, sender, user, message):
            self.server.logger.info("[Statistics] %s", message)

        def _251(self, sender, user, message):
            self.server.logger.info("[Users] %s", message)

        def _252(self, sender, user, op_number, message):
            self.server.logger.info("[Ops] There are %s IRC Operators online", op_number)

        def _253(self, sender, user, unknown_number, message):
            self.server.logger.info("[Connections] There are %s unknown connection(s)", unknown_number)

        def _254(self, sender, user, channel_number, message):
            self.server.logger.info("[Channels] There are %s channels formed", channel_number)

        def _255(self, sender, user, message):
            self.server.logger.info("[Clients] %s", message)

        def _265(self, sender, user, localnumber, localmax, message):
            self.server.logger.info("[Local] Current local users %s, max %s", localnumber, localmax)

        def _266(self, sender, user, globalnumber, globalmax, message):
            self.server.logger.info("[Global] Current global users %s, max %s", globalnumber, globalmax)

        def _315(self, sender, target, channel, info):
            self.server.logger.info("[End of WHO to %s] %s", channel, info)

        def _332(self, sender, target, channel, topic):
            self.server.logger.info("Topic of %s is %s", channel, topic)
            self.server.channels[channel].topic = topic

        def _333(self, sender, target, channel, person, lastchanged):
            self.server.logger.info("The topic was last changed %s by %s",
                         datetime.datetime.fromtimestamp(int(lastchanged)).isoformat(' '), person)
            self.server.channels[channel].topicchanged = \
                datetime.datetime.fromtimestamp(int(lastchanged))
            self.server.channels[channel].topicchanger = person

        def _352(self, sender, target, channel, ident, host, server, nick, heregone, realname):
            user = self.server.users[nick]
            user.ident = ident
            user.hostname = host
            user.realname = realname.split(" ", 1)[1]
            user.away = heregone[0] == 'G'
            self.server.logger.info("[Who] %s%s in %s is %s@%s (%s)",
                                    nick, " (away)" if user.away else "", channel,
                                    user.ident, user.hostname, user.realname)

        def _353(self, sender, target, equalsign, channel, users_on_channel):
            users = users_on_channel.split(' ')
            self.server.logger.info("Users currently in %s: %s", channel, users)

            for username in users:
                if username[0] in self.server.supported["PREFIX"]:
                    username = username[1:]

                if username in self.server.users:
                    user = self.server.users[username]
                else:
                    user = User(username, self.server)

                user.add_channel(self.server.channels[channel])

        def _354(self, sender, target, ident, host, nick, heregone, account, realname):
            user = self.server.users[nick]
            user.ident = ident
            user.hostname = host
            user.realname = realname
            user.away = heregone == 'G'
            user.account = account if account != '0' else None
            self.server.logger.info("[Whox] %s%s is %s@%s (%s) and %s",
                                    nick, " (away)" if user.away else "",
                                    user.ident, user.hostname, user.realname,
                                    "logged in as {}".format(user.account)
                                    if user.account is not None else "not logged in")

        def _366(self, sender, target, channel, message):
            self.server.logger.info("End of NAMES")

        def _372(self, sender, target, message):
            self.server.logger.info("[MOTD] %s", message)

        def _375(self, sender, target, message):
            self.server.logger.info("[MOTD] Message of the day:")

        def _376(self, sender, target, message):
            self.server.logger.info("[MOTD] End of message of the day")

        def _433(self, sender, target, nick, message):
            self.server.logger.info("[433] Username %s already in use", nick)
            if not self.server.welcomed:
                if (nick.startswith(self.server.original_username)
                        and nick[len(self.server.original_username):].isdigit()):
                    self.server.username = "{}{}".format(
                        self.server.original_username,
                        int(nick[len(self.server.original_username):]) + 1)
                else:
                    self.server.username = self.server.original_username + "1"
                self.server.nick(self.server.username)

        def _default(self, msgtype, sender, *message):
            self.server.logger.info("Unsupported message %s sent by user %s: %s", msgtype, sender, message)

        def __call__(self, msgtype, *message):
            f = getattr(self, msgtype, None)
            if f is None:
                f = getattr(self, "_" + msgtype, None)
            if f is None:
                self._default(msgtype, *message)
                return False
            else:
                f(*message)
                return True



class Channel:

    def __init__(self, channelname):
        self.channelname = channelname
        self.users = CaseInsensitiveDict()
        self.topic = None
        self.topicchanged = None
        self.topicchanger = None
        self.modes = set()

    def __repr__(self):
        return self.channelname

class User:

    def __init__(self, username, server, access=1, ident=None, hostname=None):
        self.username = username
        self.access = access
        self.ident = ident
        self.hostname = hostname
        self.server = server
        self.knownchannels = CaseInsensitiveDict()
        self.realname = None
        self.idletime = None
        self.onlinetime = None
        self.account = None
        self.away = None
        self.usermodes = set()

    def add_channel(self, channel):
        if self.username not in self.server.users:
            self.server.users[self.username] = self

        self.knownchannels[channel.channelname] = channel
        channel.users[self.username] = self

    def remove_channel(self, channel):

        del self.knownchannels[channel.channelname]
        del channel.users[self.username]

        if self is self.server.ownuser:
            for user in list(channel.users.values()):
                if user is not self:
                    user.remove_channel(channel)
            del self.server.channels[channel.channelname]
        else:
            if len(self.knownchannels) == 0:
                del self.server.users[self.username]

    def rename(self, newnick):
        del self.server.users[self.username]
        for channel in self.knownchannels.values():
            del channel.users[self.username]

        self.username = newnick

        self.server.users[self.username] = self
        for channel in self.knownchannels.values():
            channel.users[self.username] = self

    def __repr__(self):
        return self.username


class CaseInsensitiveDict(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key.lower(), value)

        def __getitem__(self, key):
            return super().__getitem__(key.lower())

        def __contains__(self, key):
            return super().__contains__(key.lower())

        def __delitem__(self, key):
            super().__delitem__(key.lower())


@asyncio.coroutine
def fetch_url(url, *, method="GET", timeout=10, **kwargs):
    res = yield from asyncio.wait_for(aiohttp.request(method, url, **kwargs), timeout)
    return (yield from res.read_and_close())
