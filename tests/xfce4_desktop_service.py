#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  xfce4-desktop-service
#
#  Copyright 2020 Thomas Castleman <contact@draugeros.org>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
"""Desktop Service for xfce4

This service provides desktop icon's functionality in the absence of Thunar
"""
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from subprocess import Popen
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import GLib, GObject, Gtk, Gdk
from sys import argv, stderr
from shutil import copyfile, rmtree, SameFileError
from pwd import getpwuid
import os
import magic
import signal
import urllib.parse

# Octal Translation Dict
octal_perms = {0: "No Permissions",
               1: "Execute",
               2: "Write",
               3: "Write, Execute",
               4: "Read",
               5: "Read, Execute",
               6: "Read, Write",
               7: "Full Permissions"}
# PID File location
pid_file = "/tmp/xfce4-desktop-service.pid"


class signal_handlers(dbus.service.Object):
    """Signal Handlers for DBus"""

    @dbus.service.method("org.xfce.FileManager1", in_signature='ass', out_signature='')
    def ShowFolders(self, uris, startupId):
        """Open folder passed in the default file manager"""
        xdg_open(uris[0])

    @dbus.service.method("org.xfce.FileManager1", in_signature='ass', out_signature='')
    def ShowItems(self, uris, startupId):
        """Open items passed in with the default method"""
        xdg_open(uris[0])

    @dbus.service.method("org.xfce.FileManager1", in_signature='ass', out_signature='')
    def ShowItemProperties(self, uris, startupId):
        """Show Properties of Item"""
        xdg_open(uris[0])

    @dbus.service.method("org.xfce.FileManager1", in_signature='', out_signature='')
    def Exit(self):
        """Quit"""
        mainloop.quit()

    @dbus.service.method("org.xfce.FileManager", in_signature='sss', out_signature='')
    def Launch(self, uri, display, startup_id):
        """Launch uri"""
        xdg_open(uri)

    @dbus.service.method("org.xfce.FileManager", in_signature='ssasss', out_signature='')
    def Execute(self, working_directory, uri, filenames, display, startup_id):
        """Execute uri"""
        xdg_open(uri)

    @dbus.service.method("org.xfce.FileManager", in_signature='sasss', out_signature='')
    def LaunchFiles(self, working_directory, filenames, display, startup_id):
        """Launch multiple files"""
        for each in filenames:
            xdg_open(each)

    @dbus.service.method("org.xfce.FileManager", in_signature='sss', out_signature='')
    def DisplayFolder(self, uri, display, startup_id):
        """Open Folder"""
        xdg_open(uri)

    @dbus.service.method("org.xfce.FileManager", in_signature='sasasss', out_signature='')
    def CopyTo(self, working_directory, source_files, target_files, display, startup_id):
        """Copy files from Point A to Point B"""
        for each in range(len(source_files)):
            if source_files[each][:7] == "file://":
                source_files[each] = source_files[each][7:]
            source_files[each] = urllib.parse.unquote(source_files[each])
            if target_files[each][:7] == "file://":
                target_files[each] = target_files[each][7:]
            target_files[each] = urllib.parse.unquote(target_files[each])
            try:
                copyfile(source_files[each], target_files[each])
            except SameFileError:
                pass

    @dbus.service.method("org.xfce.FileManager", in_signature='ssss', out_signature='')
    def CreateFile(self, parent_directory, content_type, display, startup_id):
        """Create a New File"""
        name = show_naming_GUI(content_type, None)

        if content_type == "inode/directory":
            is_directory = True
        else:
            is_directory = False

        _custom_create_file(parent_directory, name, is_directory)
        

    @dbus.service.method("org.xfce.FileManager", in_signature='sasss', out_signature='')
    def UnlinkFiles(self, working_directory, filenames, display, startup_id):
        """Delete multiple files"""
        for each in filenames:
            if each[:7] == "file://":
                each = each[7:]
            each = urllib.parse.unquote(each)
            try:
                os.remove(each)
            except IsADirectoryError:
                rmtree(each)

    @dbus.service.method("org.xfce.FileManager", in_signature='sss', out_signature='')
    def RenameFile(self, filename, display, startup_id):
        """Rename a file"""
        filename = urllib.parse.unquote(filename)
        self._custom_rename_file(filename)

    @dbus.service.method("org.xfce.FileManager", in_signature='ssss', out_signature='')
    def CreateFileFromTemplate(self, parent_directory, template_path, display, startup_id):
        """Create a new file from the specified template"""
        template_path = template_path.split("/")
        parent_directory = parent_directory + "/" + template_path[-1]
        template_path = "/".join(template_path)
        self.CopyTo(None, [template_path], [parent_directory], None, None)
        result = self._custom_rename_file(parent_directory)
        if result == 1:
            self.UnlinkFiles("", [parent_directory], "", "")


    @dbus.service.method("org.xfce.Trash", in_signature='ss', out_signature='')
    def DisplayTrash(self, display, startup_id):
        """Open Trash folder"""
        Popen(["xdg-open", "trash://"])

    @dbus.service.method("org.xfce.Trash", in_signature='asss', out_signature='')
    def MoveToTrash(self, filenames, display, startup_id):
        """Move file/folder to trash"""
        args = ["gio", "trash"]
        for uri in filenames:
            path = str(uri)
            if path.startswith('file://'):
                path = path[7:]
            path = urllib.parse.unquote(path)
            args.append(path)
            if os.fork() == 0:
                Popen(args)
                args = ["gio", "trash"]
                os._exit(0)
            else:
                os.wait()
            args = ["gio", "trash"]

    @dbus.service.method("org.xfce.Trash", in_signature='ss', out_signature='')
    def EmptyTrash(self, display, startup_id):
        """Empty trash"""
        Popen(["gio", "trash", "--empty"])

    @dbus.service.method("org.xfce.FileManager", in_signature='sss', out_signature='')
    def DisplayFileProperties(self, uri, display, startup_id):
        """Show file properties"""
        path = str(uri)
        if path.startswith('file://'):
            path = path[7:]
        path = urllib.parse.unquote(path)
        show_properties_GUI(path)

    def _custom_create_file(self, parent_directory, file_name, is_directory):
        if file_name[-1] == 1:
            return
        if isinstance(file_name, list):
            file_name = file_name[0]

        if parent_directory[:7] == "file://":
            parent_directory = parent_directory[7:]
        parent_directory = urllib.parse.unquote(parent_directory)

        if is_directory:
            os.mkdir(parent_directory + "/" + file_name)
        else:
            with open(parent_directory + "/" + file_name, "w+") as new_file:
                    new_file.write("")

    def _custom_rename_file(self, file_name):
        '''renames a file'''
        file_name = str(file_name)
        if file_name.startswith('file://'):
            path = file_name[7:]
        else:
            path = file_name
        path = urllib.parse.unquote(path)
        if os.path.isdir(path):
            content_type = "inode/directory"
        else:
            content_type = "file"
        name = show_naming_GUI(content_type, (path.split("/"))[-1])
        if name[-1] == 1:
            return 1
        name = name[0]
        new_path = path.split("/")
        del new_path[-1]
        new_path = "/".join(new_path)
        new_path = new_path + "/" + name
        os.rename(path, new_path)
        return 0

class naming_GUI(Gtk.Window):
    """UI for naming Files/Folders"""
    def __init__(self, content_type, name):
        if content_type == "inode/directory":
            content_type = "directory"
        else:
            content_type = "file"

        if name is None:
            if content_type == "file":
                name = "Untitled File"
            elif content_type == "directory":
                name = "Untitled Folder"

        self.content_type = content_type

        # Initialize the Window
        Gtk.Window.__init__(self, title="Desktop Service")
        self.grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.grid)
        self.set_icon_name("desktop-environment-xfce")

        self.label = Gtk.Label()
        self.label.set_markup("""
    What would you like to name this %s?\t""" % (content_type))
        self.label.set_justify(Gtk.Justification.LEFT)
        self.grid.attach(self.label, 1, 1, 3, 1)

        self.name = Gtk.Entry()
        self.name.set_text(name)
        self.name.set_can_default(False)
        self.name.set_can_focus(True)
        self.name.set_activates_default(True)
        self.grid.attach(self.name, 1, 2, 3, 1)
        self.name.grab_focus()

        # enable window to receive key press events
        self.connect("key-press-event", self.on_key_press_event)

        button1 = Gtk.Button.new_with_label("Okay -->")
        button1.connect("clicked", self.done)
        button1.set_can_default(True)
        self.grid.attach(button1, 3, 3, 1, 1)

        button2 = Gtk.Button.new_with_label("Exit")
        button2.connect("clicked", self.exit)
        button2.set_can_default(False)
        self.grid.attach(button2, 1, 3, 1, 1)

        self.set_name = None

        self.set_default(button1)
        # button1.grab_default() would be the preferred way to set default
        # but that function does not seem to work properly at this time

    def on_key_press_event(self, widget, event):
        """Handles keyy press events for window"""
        if event.keyval == Gdk.KEY_Escape:
            self.exit("esc key pressed")

    def done(self, button):
        """Return Data"""
        self.set_name = [self.name.get_text(), 0]
        if "/" not in self.set_name[0]:
            self.destroy()
            Gtk.main_quit("delete-event")
            return self.set_name
        self.label.set_markup("""
    What would you like to name this %s?\t

    Character `/' not allowed in %s names.\t""" % (self.content_type,
                                                   self.content_type))
        self.show_all()

    def exit(self, message):
        """Exit UI"""
        self.set_name = [1]
        self.destroy()
        Gtk.main_quit("delete-event")
        return self.set_name

class properties_GUI(Gtk.Window):
    """Properties GUI"""
    def __init__(self, file_path):
        """Initialize Properties GUI"""
        self.file_path = file_path
        self.file_name = self.file_path.split("/")[-1]
        mime = magic.Magic(mime=True)

        try:
            self.file_mime = mime.from_file(self.file_path)
            self.file_size = os.path.getsize(self.file_path)
        except IsADirectoryError:
            self.file_mime = "inode/directory"
            self.file_size = None

        self.file_permissions = str(oct(os.stat(self.file_path).st_mode)[-3:])
        self.file_owner = getpwuid(os.stat(self.file_path).st_uid).pw_name
        self.file_group = getpwuid(os.stat(self.file_path).st_gid).pw_name

        Gtk.Window.__init__(self, title="Desktop Service")

        # enable window to receive key press events
        self.connect("key-press-event", self.on_key_press_event)

        self.grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.page0 = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.page1 = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.grid)
        self.set_icon_name("desktop-environment-xfce")

        self.main()

    def on_key_press_event(self, widget, event):
        """Handles keyy press events for window"""
        if event.keyval == Gdk.KEY_Escape:
            self.exit("esc key pressed")

    def main(self):
        """Main properties window"""
        self.stack = Gtk.Stack()
        self.stack.add_titled(self.page0, "page0", "Basic")
        self.stack.add_titled(self.page1, "page1", "Permissions")
        self.grid.attach(self.stack, 1, 2, 4, 1)

        self.stack_switcher = Gtk.StackSwitcher()
        self.stack_switcher.set_stack(self.stack)
        self.grid.attach(self.stack_switcher, 2, 1, 2, 1)

        self.label = Gtk.Label()
        self.label.set_markup("""\n\tName:\t""")
        self.label.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label, 1, 1, 1, 1)

        self.label1 = Gtk.Label()
        self.label1.set_markup("\n\t" + self.file_name + "\t")
        self.label1.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label1, 2, 1, 1, 1)

        self.label2 = Gtk.Label()
        self.label2.set_markup("""\n\tType:\t""")
        self.label2.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label2, 1, 2, 1, 1)

        self.label3 = Gtk.Label()
        self.label3.set_markup("\n\t" + self.file_mime + "\t")
        self.label3.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label3, 2, 2, 1, 1)

        self.label4 = Gtk.Label()
        self.label4.set_markup("""\n\tLocation:\t""")
        self.label4.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label4, 1, 3, 1, 1)

        self.label5 = Gtk.Label()
        self.label5.set_markup("\n\t" + self.file_path + "\t")
        self.label5.set_justify(Gtk.Justification.LEFT)
        self.page0.attach(self.label5, 2, 3, 1, 1)

        self.label6 = Gtk.Label()
        self.label6.set_markup("""\n\tOwner:\t""")
        self.label6.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label6, 1, 1, 1, 1)

        self.label7 = Gtk.Label()
        self.label7.set_markup("\n\t" + self.file_owner + "\t")
        self.label7.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label7, 2, 1, 1, 1)

        perms = translate_full_octal(self.file_permissions)
        owner_perms = perms[0]
        group_perms = perms[1]
        public_perms = perms[2]

        self.label8 = Gtk.Label()
        self.label8.set_markup("""\n\tOwner\n\tPermissions:\t""")
        self.label8.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label8, 1, 2, 1, 1)

        self.label9 = Gtk.Label()
        self.label9.set_markup("\n\t" + owner_perms + "\t")
        self.label9.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label9, 2, 2, 1, 1)

        self.label10 = Gtk.Label()
        self.label10.set_markup("""\n\tGroup:\t""")
        self.label10.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label10, 1, 3, 1, 1)

        self.label11 = Gtk.Label()
        self.label11.set_markup("\n\t" + self.file_group + "\t")
        self.label11.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label11, 2, 3, 1, 1)

        self.label12 = Gtk.Label()
        self.label12.set_markup("""\n\tGroup\n\tPermissions:\t""")
        self.label12.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label12, 1, 4, 1, 1)

        self.label13 = Gtk.Label()
        self.label13.set_markup("\n\t" + group_perms + "\t")
        self.label13.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label13, 2, 4, 1, 1)

        self.label14 = Gtk.Label()
        self.label14.set_markup("""\n\tPublic\n\tPermissions:\t""")
        self.label12.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label14, 1, 5, 1, 1)

        self.label15 = Gtk.Label()
        self.label15.set_markup("\n\t" + public_perms + "\t")
        self.label15.set_justify(Gtk.Justification.LEFT)
        self.page1.attach(self.label15, 2, 5, 1, 1)

        self.button1 = Gtk.Button.new_with_label("Delete")
        self.button1.connect("clicked", self.delete)
        self.grid.attach(self.button1, 4, 3, 1, 1)

        self.button2 = Gtk.Button.new_with_label("Exit")
        self.button2.connect("clicked", self.exit)
        self.grid.attach(self.button2, 1, 3, 1, 1)

    def delete(self, button):
        """Delete current file/folder"""
        try:
            os.remove(self.file_path)
        except IsADirectoryError:
            rmtree(self.file_path)

        self.exit("clicked")

    def exit(self, message):
        """close properties GUI"""
        self.set_name = [1]
        self.destroy()
        Gtk.main_quit("delete-event")

def xdg_open(uri):
    """Open the URI using the default method"""
    args = ['xdg-open']
    path = str(uri)
    if path.startswith('file://'):
        path = path[7:]
    if "%20" in path:
        path = path.split("%20")
        path = " ".join(path)
    args.append(path)
    if os.fork() == 0:
        Popen(args)
        os._exit(0)
    else:
        os.wait()

def File_Manager():
    """Start up DBus listeners"""
    try:
        signal.signal(signal.SIGTERM, killer_signal_handler)
        DBusGMainLoop(set_as_default=True)

        bus = dbus.SessionBus()
        name = dbus.service.BusName("org.xfce.FileManager", bus)
        object = signal_handlers(bus, '/org/xfce/FileManager')

        mainloop = GLib.MainLoop()
        mainloop.run()
    except:
        killer_signal_handler("", "")

def show_naming_GUI(content_type, file_name):
    """Show the Naming GUI"""
    window = naming_GUI(content_type, file_name)
    window.set_decorated(True)
    window.set_resizable(False)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.connect("delete-event", naming_GUI.exit)
    window.show_all()
    Gtk.main()
    return window.set_name

def show_properties_GUI(file_path):
    """Display the properties GUI for the file at file_path"""
    window = properties_GUI(file_path)
    window.set_decorated(True)
    window.set_resizable(False)
    window.set_position(Gtk.WindowPosition.CENTER)
    window.connect("delete-event", properties_GUI.exit)
    window.show_all()
    Gtk.main()


def eprint(*args, **kwargs):
    """Make it easier for us to print to stderr"""
    print(*args, file=stderr, **kwargs)


def translate_full_octal(octal):
    """Convert Full octal perms to Human readable format, in an array

     Index 0 is USER perms
     Index 1 is GROUP perms
     Index 2 is PUBLIC perms
    """
    try:
        if len(octal) > 3:
            raise ValueError("Not a valid octal permission set. Too Long. :  %s " % (octal))
    except TypeError:
        pass
    if not isinstance(octal, str):
        octal = oct(octal)[2:]
    output = []
    for each in octal:
        output.append(octal_perms[int(each)])
    if len(octal) > 3:
        raise ValueError("Not a valid octal permission set. Too Long. :  %s " % (octal))
    return output


def killer_signal_handler(signal, frame):
    """Handle Closing signals"""
    os.remove(pid_file)


if __name__ == '__main__':
    #get length of argv
    argc = len(argv)
    VERSION = "0.1.5-alpha1"
    HELP = """xfce4-desktop-service, Version: %s

    -b, --background        Start service in the background.
    -h, --help              Show this help dialog and exit.
    -k, --kill              Kill currently running background process.
    -v, --version           Show the current version.

    Pass nothing to start the desktop service on the current process.""" % (VERSION)
    if argc <= 1:
        if not os.path.isfile(pid_file):
            with open(pid_file, "w+") as file:
                file.write(str(os.getpid()))
        File_Manager()
    elif ((argv[1] == "-h") or (argv[1] == "--help")):
        print(HELP)
    elif ((argv[1] == "-v") or (argv[1] == "--version")):
        print(VERSION)
    elif ((argv[1] == "-b") or (argv[1] == "--background")):
        process = Popen("xfce4-desktop-service")
        with open(pid_file, "w+") as file:
            file.write(str(process.pid))
    elif ((argv[1] == "-k") or (argv[1] == "--kill")):
        if not os.path.isfile(pid_file):
            eprint("ERROR: No currently running background process.")
            exit(2)
        with open(pid_file, "r") as file:
            pid = file.read()
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            eprint("ERROR: No currently running background process.")
            os.remove(pid_file)
            exit(2)
        os.remove(pid_file)
    else:
        eprint("%s :  argument not recognized" % (argv[1]))
        print(HELP)
