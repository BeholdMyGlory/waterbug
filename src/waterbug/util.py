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

import itertools

def reduce_until(function, iterable, initializer, condition=lambda x, y: True):
    a = initializer
    iterator = iter(iterable)
    prev = []
    for i in iterator:
        if not condition(a, i):
            prev = [i]
            break
        a = function(a, i)

    return (a, prev + list(iterator))


def all_in(a, b):
            for i in a:
                if i not in b:
                    return False

            return True

def pad_iter(iterable, length, default=None):
    return itertools.islice(itertools.chain(iterable, itertools.repeat(default)), length)
