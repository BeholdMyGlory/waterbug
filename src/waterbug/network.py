import asynchat
from datetime import datetime
import itertools
import logging
import socket
import traceback

import waterbug.waterbug

class Server(asynchat.async_chat):
    
    def __init__(self, server, port, connection_name, bot, username="Waterbug",
                 ident={"user": "waterbug", "hostname": "-", "servername": "-",
                        "realname": "Waterbug"}, inencoding="irc", outencoding="utf8"):
        super().__init__()
        
        self.channels = CaseInsensitiveDict()
        self.users = CaseInsensitiveDict()
        self.inencoding = inencoding
        self.outencoding = outencoding
        self.conection_name = connection_name
        self.bot = bot
        self.username = username
        self.ident = ident
        
        self.supported = {}
        
        self.receiver = Server.MessageReceiver(self)
        
        self.buffer = bytearray()
        self.inbuffer = bytearray()
        self.lastline = ''
        
        self.set_terminator(b"\r\n")
        self.server_address = (server, port)
        
    
    def connect(self):
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        super().connect(self.server_address)
        
        self.nick(self.username)
        self.user(self.ident)
    
    
    def msg(self, target, message):
        message = ''.join(map(lambda x: '[{}]'.format(ord(x)) if x < ' ' else x, message))
        self.write("PRIVMSG {} :{}".format(target, message))
    
    def join(self, channel):
        self.write("JOIN {}".format(channel))
    
    def part(self, channel):
        self.write("PART {}".format(channel))
    
    def nick(self, nick):
        self.write("NICK :{}".format(nick))
    
    def user(self, ident):
        self.write("USER {} {} {} :{}".format(ident["user"], ident["hostname"],
                                              ident["servername"], ident["realname"]))
    
    
    def handle_connect(self):
        logging.info("Connected to %s", self.server_address[0])
    
    def handle_close(self):
        logging.info("Closing connection to %s", self.server_address[0])
        self.close()
    
    def handle_error(self):
        traceback.print_exc()
        logging.error("Last line: %s", self.lastline)
        self.close()
    
    def collect_incoming_data(self, data):
        self.inbuffer.extend(data)
    
    def found_terminator(self):
        data = bytes(self.inbuffer)
        self.inbuffer = bytearray()
        
        self.lastline = data
        
        if self.inencoding == "irc":
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin", "replace")
        else:
            text = data.decode(self.inencoding)
        
        self.lastline = text
        
        if text.startswith(":"):
            (username, msgtype, *parameters) = text[1:].split(' ') #remove starting :
            (username, *host) = username.split("!", 2)
            host = None if len(host) == 0 else host[0]
            ident = None
            access = waterbug.waterbug.STANDARD
            if host is not None:
                (ident, host) = host.split("@", 2)
                if host in self.bot.privileges:
                    access = self.bot.privileges[host]
            
            if username in self.users:
                user = self.users[username]
                if host is not None:
                    user.hostname = host
                if ident is not None:
                    user.ident = ident
                user.access = access
            else:
                user = User(username, access, ident, host)
            
            for i, v in enumerate(parameters):
                if v[0].startswith(":"):
                    #remove the : and join together all succeeding parameters
                    #into one long parameter
                    parameters[i:] = [' '.join([v[1:]] + parameters[i + 1:])]
                    break
            
            self.receiver(msgtype, user, *parameters)
        else:
            logging.info("Server sent: %s", text)
            if text.startswith("PING"):
                self.write("PONG " + text.split(' ')[1])
    
    def writable(self):
        return len(self.buffer) > 0
    
    def handle_write(self):
        if len(self.buffer) > 0:
            self.send(self.buffer)
            self.buffer = bytearray()
    
    def write(self, line):
        logging.info(">> %s", line)
        self.buffer.extend(bytes(line, self.outencoding))
        self.buffer.extend(b"\r\n")
        
    class MessageReceiver:
        
        def __init__(self, server):
            self.server = server
    
        def PRIVMSG(self, sender, target, message):
            logging.info("<%s to %s> %s", sender, target, message)
            self.server.bot.on_privmsg(self.server, sender, target, message)
        
        def NOTICE(self, sender, target, message):
            logging.info("[NOTICE] <%s to %s> %s", sender, target, message)
        
        def JOIN(self, sender, channel):
            logging.info("%s joined channel %s", sender, channel)
            
            # On join we want to 1) if the sender is the own user,
            # create a new Channel object and add it to the channels
            # list. 2) If the joining user is not already in the users
            # list, add the user to the list. 3) Add the channel to the
            # user's list of known channels. 4) Add the user to the
            # channel's list of users.
            
            # 1
            if sender is self.server.ownuser:
                self.server.channels[channel] = Channel(channel)
            
            # 2
            if sender.username not in self.server.users:
                self.server.users[sender.username] = sender
            
            # 3
            sender.knownchannels[channel] = self.server.channels[channel]
            # 4
            self.server.channels[channel].users[sender.username] = sender
        
        def PART(self, sender, channel, message=""):
            logging.info("%s parted from channel %s with message %s", sender, channel, message)
            
            # On part we need to 1) remove the parted channel from sender
            # as well as 2) remove the sender from the channel. 3) Unless
            # the sender is the own user, if the sender has no more known
            # channels left we want to remove the sender completely from
            # the users list. 4) If the sender is the own user, we want to
            # 5) remove the channel from all users in the channel,
            # 6) for each user check if they have no known channels left
            # and in that case remove the user from the users list and
            # 7) remove the channel from the channels list.
            
            # 1
            del sender.knownchannels[channel]
            # 2
            del self.server.channels[channel].users[sender.username]
            # 3
            if len(sender.knownchannels) == 0 and sender is not self.server.ownuser:
                del self.server.users[sender.username]
            
            # 4
            if sender is self.server.ownuser:
                # 5
                for user in self.server.channels[channel].users.values():
                    if user is not sender:  # we already removed it for this user
                                            # at the top of the method
                        del user.knownchannels[channel]
                        # 6
                        if len(user.knownchannels) == 0:
                            del self.server.users[user.username]
                # 7
                del self.server.channels[channel]
        
        def KICK(self, sender, channel, kickee, message=""):
            logging.info("%s kicked %s from channel %s with message %s", sender, kickee, channel, message)
            self.PART(self.server.users[kickee], channel, message)
        
        def QUIT(self, sender, message=""):
            logging.info("User %s quit with message %s", sender, message)
            
            # On quit we need to: 1) For all channels in the quitting user's
            # channel list, remove the user from the channel. 2) Remove the
            # user from users list
            
            # 1
            for channel in sender.knownchannels.values():
                del channel.users[sender.username] 
            
            # 2
            del self.server.users[sender.username]
        
        def NICK(self, sender, message):
            logging.info("User %s changed nick to %s", sender, message)
            
            # When a user changes his nickname, we must 1) update the nickname
            # of the sender to the new nick, 2) add the sender
            # to the users array with the new nick as the key and 3) remove
            # the old key from the users list. We must then 4) for each channel
            # that the user has joined, 5) remove the key of the old nickname
            # and 6) add the user to the channel using the new nickname as
            # the key.
            
            oldnick = sender.username
            
            # 1
            sender.username = message
            # 2
            self.server.users[message] = sender
            # 3
            del self.server.users[oldnick]
            
            # 4
            for channel in sender.knownchannels.values():
                # 5
                del channel[oldnick]
                # 6
                channel[sender.username] = sender
        
        def _001(self, sender, user, message):
            logging.info("[Welcome] %s", message)
            self.server.ownuser = User(user)
            self.server.users[user] = self.server.ownuser
        
        def _002(self, sender, user, message):
            logging.info("[Host] %s", message)
        
        def _003(self, sender, user, message):
            logging.info("[Created] %s", message)
        
        def _004(self, sender, user, host, version, usermodes, chanmodes, *supported):
            logging.info("[My Info] I am %s running %s. User modes: %s. Channel modes: %s",
                         host, version, usermodes, chanmodes)
        
        def _005(self, sender, user, *message):
            logging.info("[Supported] %s", message)
            for i in itertools.islice(message, len(message)-1):
                a = i.split("=", 2)
                if len(a) == 2:
                    self.server.supported[a[0]] = a[1]
                else:
                    self.server.supported[a[0]] = True
        
        def _250(self, sender, user, message):
            logging.info("[Statistics] %s", message)
        
        def _251(self, sender, user, message):
            logging.info("[Users] %s", message)
        
        def _252(self, sender, user, op_number, message):
            logging.info("[Ops] There are %s IRC Operators online", op_number)
        
        def _253(self, sender, user, unknown_number, message):
            logging.info("[Connections] There are %s unknown connection(s)", unknown_number)
        
        def _254(self, sender, user, channel_number, message):
            logging.info("[Channels] There are %s channels formed", channel_number)
        
        def _255(self, sender, user, message):
            logging.info("[Clients] %s", message)
        
        def _265(self, sender, user, localnumber, localmax, message):
            logging.info("[Local] Current local users %s, max %s", localnumber, localmax)
        
        def _266(self, sender, user, globalnumber, globalmax, message):
            logging.info("[Global] Current global users %s, max %s", globalnumber, globalmax)
            
        def _332(self, sender, target, channel, topic):
            logging.info("Topic of %s is %s", channel, topic)
            self.server.channels[channel].topic = topic
        
        def _333(self, sender, target, channel, person, lastchanged):
            logging.info("The topic was last changed %s by %s", datetime.fromtimestamp(int(lastchanged)).isoformat(' '), person)
            self.server.channels[channel].topicchanged = datetime.fromtimestamp(int(lastchanged))
            self.server.channels[channel].topicchanger = person
        
        def _353(self, sender, target, equalsign, channel, users_on_channel):
            users = users_on_channel.split(' ')
            logging.info("Users currently in %s: %s", channel, users)
            
            # For each user in the channel we need to: 1) Check if the nickname
            # begins with a prefix, and if so remove the prefix. 2) If the
            # nickname exists in the users list, get the user from the list,
            # 3) otherwise create a user object and add it to the users list.
            # 4) Add the channel to the user's known channels. 5) Add the
            # user to the channel's list of users
            
            for username in users:
                # 1
                if username[0] in self.server.supported["PREFIX"]:
                    username = username[1:]
                
                # 2
                if username in self.server.users:
                    user = self.server.users[username]
                # 3
                else:
                    user = User(username)
                    self.server.users[username] = user
                # 4
                user.knownchannels[channel] = self.server.channels[channel]
                # 5
                self.server.channels[channel].users[user.username] = user
        
        def _366(self, sender, target, channel, message):
            logging.info("End of NAMES")
        
        def _372(self, sender, target, message):
            logging.info("[MOTD] %s", message)
        
        def _375(self, sender, target, message):
            logging.info("[MOTD] Message of the day:")
        
        def _376(self, sender, target, message):
            logging.info("[MOTD] End of message of the day")
    
        def _default(self, msgtype, sender, *message):
            logging.info("Unsupported message %s sent by user %s: %s", msgtype, sender, message)
        
        def __call__(self, msgtype, *message):
            f = getattr(self, msgtype, None)
            if f is None:
                f = getattr(self, "_" + msgtype, None)
            if f is None:
                self._default(msgtype, *message)
            else:
                f(*message)
    
    

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
    
    def __init__(self, username, access=1, ident=None, hostname=None):
        self.username = username
        self.access = access
        self.ident = ident
        self.hostname = hostname
        self.knownchannels = CaseInsensitiveDict()
        self.realname = None
        self.idletime = None
        self.onlinetime = None
        self.identified = None
        self.awaystatus = None
        self.usermodes = set()
    
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

