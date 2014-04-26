
__all__ = ["PRIVMSG", "NOTICE", "JOIN", "PART", "QUIT", "KICK", "NICK",
           "BANNED", "STANDARD", "TRUSTED", "ELEVATED", "OP", "ADMIN"]

PRIVMSG = 1 << 0
NOTICE  = 1 << 1
JOIN    = 1 << 2
PART    = 1 << 3
QUIT    = 1 << 4
KICK    = 1 << 5
NICK    = 1 << 6

BANNED = 0
STANDARD = 1
TRUSTED = 2
ELEVATED = 3
OP = 4
ADMIN = 5
