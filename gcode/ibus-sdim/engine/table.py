# -*- coding: utf-8 -*-
# vim:et sts=4 sw=4
#
# ibus-sdim - The Tables engine for IBus
#
# Copyright (c) 2008-2009 Yu Yuwei <acevery@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# $Id: $
#
__all__ = (
    "tabengine",
)

def _str_percent_decode(str):
    return str.replace("%20", " ").replace("%25", "%")


import os
from gi.repository import IBus
from curses import ascii
#from ibus import Property
import keysyms
import re

from gettext import dgettext
_  = lambda a : dgettext ("ibus-sdim", a)
N_ = lambda a : a

import dbus
from socket import *

class KeyEvent:
    all_mods = [
        '', #no modifier
        'A', # alt
        'AC',# alt ctrl
        'ACS', #alt ctrl shift
        'AS',
        'C',
        'CS',
        'S'
        ]
    def __init__(self, keyval, is_press, state):
        self.code = keyval
        self.mask = state
        self.name = ''
        if not is_press:
            self.mask |= IBus.ModifierType.RELEASE_MASK
            return

        try:
            self.name = chr(self.code)
            if self.name == ' ':
                self.name = 'space'
            else:
                self.mask &= ~IBus.ModifierType.SHIFT_MASK
        except:
            self.name = keysyms.keycode_to_name(self.code).lower()

        if self.name in ("control_l",
                         "control_r",
                         "alt_l",
                         "alt_r",
                         "shift_l",
                         "shift_r",
                         ):
            self.name = ""
            return

        mods = ''
        if self.mask & IBus.ModifierType.MOD1_MASK:
            mods += 'A'
        if self.mask & IBus.ModifierType.CONTROL_MASK:
            mods += 'C'
        if self.mask & IBus.ModifierType.SHIFT_MASK:
            mods += 'S'

        if mods != '':
            self.name = mods + ' ' + self.name
    def __str__(self):
        return self.name


class tabengine (IBus.Engine):
    '''The IM Engine for Tables'''

    _page_size = 10
    def do_connect(self):
        if self.sock:
            self.do_disconnect()
        self.sock = socket(AF_INET, SOCK_STREAM)
        self.sock.connect(("localhost", 31415))
        self.sock = self.sock.makefile("rwb", 0)

    def do_disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def __init__ (self, bus, obj_path):
        print 'obj_path is', obj_path
        super(tabengine,self).__init__ (connection=bus.get_connection(),
                                        object_path=obj_path)
        self._bus = bus
        self.sock = None

        self.do_connect()

        self.clear_data()
        self._lookup_table = IBus.LookupTable (tabengine._page_size)

        self._name = 'sdim'
        print 'name is', self._name
        self._config_section = "engine/%s" % self._name

        # config module
        self._config = self._bus.get_config ()
        self._on = True
        self.reset ()

    def clear_data(self):
        self._preedit_str = ''
        self._cands = []
        self._aux_str = ''
        self._commit_str = ''
        self._cands_str = ''
        self._cand_idx = '0'
        self._active = ''

    def reset (self):
        self._update_ui ()

    def do_destroy(self):
        self.reset ()
        self.do_focus_out ()
        self.do_disconnect()
        super(tabengine,self).destroy()

    def _update_preedit (self):
        '''Update Preedit String in UI'''
        _str = self._preedit_str
        if _str == '':
            super(tabengine, self).update_preedit_text(IBus.Text.new_from_string(''), 0, False)
        else:
            # because ibus now can only insert preedit into txt, so...
            attrs = IBus.AttrList()
            attrs.append(IBus.attr_underline_new(IBus.AttrUnderline.SINGLE, 0, len(_str)))
            text = IBus.Text.new_from_string(_str)
            i = 0
            while attrs.get(i) != None:
                attr = attrs.get(i)
                text.append_attribute(attr.get_attr_type(),
                                      attr.get_value(),
                                      attr.get_start_index(),
                                      attr.get_end_index())
                i += 1
            super(tabengine, self).update_preedit_text(text, len(_str), True)

    def _update_aux (self):
        '''Update Aux String in UI'''
        _aux = self._aux_str
        if _aux:
            attrs = IBus.AttrList()
            attrs.append(IBus.attr_foreground_new(0x9515b5, 0, len(_aux)))
            text = IBus.Text.new_from_string(_aux)
            i = 0
            while attrs.get(i) != None:
                attr = attrs.get(i)
                text.append_attribute(attr.get_attr_type(),
                                      attr.get_value(),
                                      attr.get_start_index(),
                                      attr.get_end_index())
                i += 1
            super(tabengine, self).update_auxiliary_text(text, True)
        else:
            self.hide_auxiliary_text()


    def _update_lookup_table (self):
        '''Update Lookup Sdim in UI'''
        if self._cands_str == '':
            self.hide_lookup_table()
            return

        _cands = self._cands_str.split()
        _cands = [_str_percent_decode(str) for str in _cands]

        self._lookup_table.clean()

        for cand in _cands:
            self._lookup_table.append_candidate(IBus.Text.new_from_string(cand))

        index = int(self._cand_idx) % 10
        self._lookup_table.set_cursor_pos(index)
        self._lookup_table.show_cursor(True)
        self.update_lookup_table ( self._lookup_table, True)

    def _update_ui (self):
        '''Update User Interface'''
        self._update_lookup_table ()
        self._update_preedit ()
        self._update_aux ()
        self.commit_string()

    def commit_string (self):
        if self._commit_str == '':
            return
        commit = self._commit_str
        self._commit_str = ''
        super(tabengine,self).commit_text(IBus.Text.new_from_string(commit))

    def do_process_key_event(self, keyval, keycode, state):
        '''Process Key Events
        Key Events include Key Press and Key Release,
        IBus.ModifierType.means Key Pressed
        '''
        key = KeyEvent(keyval, state & IBus.ModifierType.RELEASE_MASK == 0, state)
        # ignore NumLock mask
        key.mask &= ~IBus.ModifierType.MOD2_MASK
        result = self._process_key_event (key)
        return result

    def _process_key_event (self, key):
        '''Internal method to process key event'''
        key = str(key)
        if key == '':
            return False
        if self._preedit_str == '' and len(key) != 1:
            return False
        self._really_process_key(key)
        self._update_ui()
        return True

    def _really_process_key (self, key):
        try:
            self.sock.write("keyed " + key + "\n")
        except:
            self.do_connect()
            return
        self.clear_data()
        while True:
            try:
                line = self.sock.readline()
            except:
                self.do_connect()
                self._aux_str = "Error with sock connection"
                break
            if not line:
                break
            line = line[:-1]

            if line.find('commit: ') == 0:
                self._commit_str = line[len('commit: '):]

            elif line.find('hint: ') == 0:
                self._aux_str = line[len('hint: '):]

            elif line.find('comp: ') == 0:
                self._preedit_str = line[len('comp: '):]

            elif line.find('cands: ') == 0:
                self._cands_str = line[len('cands: '):]

            elif line.find('cand_index: ') == 0:
                self._cand_idx = line[len('cand_index: '):]

            elif line.find('active: ') == 0:
                self._active = line[len('active: '):]

            elif line == "end:":
                break

            else:
                self._aux_str = line

    def do_focus_in (self):
        if self._on:
            self._update_ui ()

    def do_focus_out (self):
        pass

    def do_enable (self):
        self._on = True
        if not self.sock:
            self.do_connect()
        self.do_focus_in()

    def do_disable (self):
        self.reset()
        self.do_disconnect()
        self._on = False

    # for further implementation :)
    @classmethod
    def CONFIG_VALUE_CHANGED(cls, bus, section, name, value):
        config = bus.get_config()
        if section != self._config_section:
            return

    @classmethod
    def CONFIG_RELOADED(cls, bus):
        config = bus.get_config()
        if section != self._config_section:
            return
