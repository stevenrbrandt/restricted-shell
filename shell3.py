#!/usr/bin/env python3 
from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE, STDOUT, call
import os
import sys
import re
from traceback import print_exc
from termcolor import colored

def here(*args):
    import inspect
    stack = inspect.stack()
    frame = stack[1]
    print("HERE: %s:%d" % (frame.filename, frame.lineno), *args, flush=True)
    frame = None
    stack = None

class ExitShell(Exception):
    def __init__(self, rc):
        self.rc = rc

import io
home = os.environ["HOME"]
log_file = os.path.join(home,"log_shell.txt")
log_fd = io.TextIOWrapper(open(log_file,"ab",0), write_through=True)
sys.stderr.flush()
#sys.stderr = open(log_file,"ab",0)

my_shell = os.path.realpath(sys.argv[0])

verbose = False
if_stack = []
short_circuit = False

sftp = "/usr/libexec/openssh/sftp-server"
sftp_alt = os.environ.get("SFTP",None)

exe_dir = re.sub(r'/*$','/',os.environ.get("EXE_DIR",os.path.join(os.environ["HOME"],"exe")))

vartable = { "word":"WORD", "?":"0" }
functable = {}
pidtable = {}

in_for = False
in_do = False
in_if = False
for_stack = []
last_ending = "\n"
the_input = ""

def unesc(s):
    n = ''
    i = 0
    while i < len(s):
        c = s[i]
        i += 1
        if i < len(s) and c == '\\':
            c2 = s[i]
            i += 1
            if c2 == 'n':
                n += '\n'
            elif c2 == 'r':
                n += '\r'
            elif c2 == 't':
                n += '\t'
            else:
                n += c2
        else:
            n += c
    return n

class Text:
    def __init__(self,s):
        self.s = s
    def __repr__(self):
        return '"'+self.s+'"'

class Redir:
    def __init__(self, fd_orig, mode, fd_new):
        self.fd_orig = fd_orig
        self.mode = mode
        self.fd_new = fd_new
    def __repr__(self):
        if self.fd_orig == sys.stdin:
            fd = "stdin"
        elif self.fd_orig == sys.stdout:
            fd = "stdout"
        elif self.fd_orig == sys.stderr:
            fd = "stderr"
        else:
            fd = str(self.fd_orig)
        return f"Redir({fd},{self.mode},{self.fd_new})"

class Space:
    def __init__(self,s):
        self.s = s
    def __repr__(self):
        return r'\s'

class Quote:
    def __init__(self,s,is_double):
        self.s = unesc(s)
        self.raw = s
        self.is_double = is_double
    def __repr__(self):
        if self.is_double:
            return '"'+self.raw+'"'
        else:
            return "'"+self.raw+"'"

class Command:
    def __init__(self, ty="exec"):
        self.args = []
        self.trimmed = False
        self.end = None
        self.redirects = []
        self.end_symbol = None
        self.type = ty
        if ty == "(":
            self.type = "proc"
        elif ty == "$(":
            self.type = "evalproc"
        elif ty == "$((":
            self.type = "calc"
        elif ty == "[":
            self.type = "test"
        elif ty == "[[":
            self.type = "test2"
        assert re.match(r'^\w+$',self.type)

    def trim(self):
        self.trimmed = True
        while len(self.args) > 0 and isinstance(self.args[0],Space):
            self.args = self.args[1:]
        while len(self.args) > 0 and isinstance(self.args[-1],Space):
            self.args = self.args[:-1]

    def pr(self,indent=0):
        if self.trimmed:
            tr = "*"
        else:
            tr = ""
        print(" "*indent,"Command",tr,":",sep='')
        print(" "*indent,"  type: ",self.type,sep='')
        print(" "*indent,"  args=[",sep='')
        for i in range(len(self.args)):
            if isinstance(self.args[i], Command):
                self.args[i].pr(indent=indent + 4)
            else:
                print(" "*(indent+4),self.args[i],sep='',end='')
            if i +1 < len(self.args):
                print(",")
            else:
                print()
        print(" "*(indent+2),"],",sep='')
        if len(self.redirects) > 0:
            print(" "*indent,"  redirects=[",sep='')
            for i in range(len(self.redirects)):
                print(" "*(indent+4),self.redirects[i])
            print(" "*(indent+2),"],",sep='')
        print(" "*(indent+2),"end: ",self.end,sep='')
        print(" "*indent,"]",sep='',end='')
        if indent==0:
            print()

    def __repr__(self):
        s = "Command(args="+str(self.args)+",end="
        if self.end == '\n':
            s += '\\n'
        else:
            s += str(self.end)
        if self.end_symbol is not None:
            s += f",end_symbol={self.end_symbol}"
        s += ",redirects="+str(self.redirects)+")"
        return s

class Shell:
    def __init__(self):
        self.lines = []
        self.program = []
        self.store = ''
        self.show = 0
        self.end_symbol = None
        self.multi_line_input = ""

    def assemble(self, args):
        i=0
        unit_type = [["",Command()],["",Command()]]
        argc = len(args)
        while i < argc:
            arg = args[i]
            if arg == "[[":
                unit_type += [["[[",Command(arg)]]
                #unit_type[-1][1].args += [arg]
            elif arg == "[":
                unit_type += [["[",Command(arg)]]
                #unit_type[-1][1].args += [arg]
            elif arg == "]]":
                assert unit_type[-1][0] == "[["
                #unit_type[-1][1].args += [arg]
                cur = unit_type[-1][1]
                cur.trim()
                unit_type = unit_type[:-1]
                unit_type[-1][1].args += [cur]
            elif arg == "]":
                assert unit_type[-1][0] == "[", str(unit_type)
                #unit_type[-1][1].args += [arg]
                cur = unit_type[-1][1]
                cur.trim()
                unit_type = unit_type[:-1]
                unit_type[-1][1].args += [cur]
            elif arg in ['$((']:
                #unit_type[-1][1].args += [arg]
                unit_type += [[arg,Command(arg)]]
            elif arg == '(' and unit_type[-1][1].type != "test2":
                unit_type += [[arg,Command(arg)],["",Command()]]
            elif arg == '$(':
                #unit_type[-1][1].args += [arg]
                unit_type += [[arg,Command(arg)],["",Command()]]
            #elif arg == '$(':
            #    unit_type += [["$(",Command()]]
            #    unit_type[-1][1].args += [arg]
            #elif arg == '$((':
            #    unit_type += [["$((",Command()]]
            #    unit_type[-1][1].args += [arg]
            elif arg == ')' and unit_type[-1][1].type != "test2":
                cur = unit_type[-1][1]
                cur.trim()
                ut = unit_type[-1][0]
                if ut == '$((':
                    assert i+1 < argc and args[i+1] == ')'
                    i += 1
                    utb = False
                else:
                    utb = True
                unit_type = unit_type[:-1]
                unit_type[-1][1].args += [cur]
                if utb:
                    cur = unit_type[-1][1]
                    cur.trim()
                    unit_type = unit_type[:-1]
                    unit_type[-1][1].args += [cur]
                #unit_type[-1][1].args += [arg]
            elif arg in ['&&', "||", "|", "&", "\n", ";"]:
                if unit_type[-1][0] == "[[":
                    unit_type[-1][1].args += [arg]
                else:
                    unit_type[-1][1].end = arg
                    cur = unit_type[-1][1]
                    cur.trim()
                    unit_type = unit_type[:-1]
                    unit_type[-1][1].args += [cur]
                    unit_type += [["",Command()]]
            elif arg == '||':
                if unit_type[-1][0] == "[[":
                    unit_type[-1][1].args += [arg]
                else:
                    unit_type[-1][1].end = arg
                    cur = [unit_type[-1][1]]
                    unit_type = unit_type[:-1]
                    unit_type[-1][1].args += [cur]
                    unit_type += [["",Command()]]
            #elif arg in ["&",";","|","\n"]:
            #    unit_type[-1][1].end = arg
            #    self.lines += [unit_type[-1][1]]
            #    unit_type = unit_type[:-1] + [["",Command()]]
            elif arg == '<<':
                off = 1
                if i + off < argc:
                    if isinstance(args[i+off],Space):
                        off += 1
                if i + off < argc:
                    self.end_symbol = args[i+off]
                    unit_type[-1][1].end_symbol = self.end_symbol
                i += off
#            elif arg == '<':
#                if unit_type[-1][0] == "[[":
#                    unit_type[-1][1].args += [arg]
#                else:
#                    off = 1
#                    assert i + off < argc, "Input redirect is missing a file"
#                    if isinstance(args[i+off],Space):
#                        off = 2
#                        assert i + off < argc, "Input redirect is missing a file"
#                    rargs = []
#                    while i+off < argc and not isinstance(args[i+off],Space):
#                        print("add off:",off)
#                        rargs += [args[i+off]]
#                        off += 1
#                    print("rargs:",rargs)
#                    unit_type[-1][1].redirects += [Redir(sys.stdin, "r", rargs)]
#                    i += off
#            elif arg == '>':
#                if unit_type[-1][0] == "[[":
#                    unit_type[-1][1].args += [arg]
#                else:
#                    assert i + 1 < argc, "Output redirect is missing a file"
#                    unit_type[-1][1].redirects += [Redir(sys.stdin, "w", args[i+1])]
#                    i += 1
#            elif arg == '>>':
#                unit_type[-1][1].redirects += [Redir(sys.stdin, "a", args[i+1])]
            else:
                unit_type[-1][1].args += [arg]
            i += 1
        #if len(unit_type[-1][1].args) > 0:
        #    self.lines += [unit_type[-1][1]]
        cur = unit_type[-1][1]
        cur.trim()
        unit_type = unit_type[:-1]
        if len(cur.args)>0:
            unit_type[-1][1].args += [cur]
        assert len(unit_type)==1, f"length is {len(unit_type)}"
        self.lines += [unit_type[0][1]]

    def process_input(self, cmd):
        if len(cmd)==0:
            return
        if self.end_symbol is not None:
            if cmd.strip() == self.end_symbol:
                self.store = ''
                self.lines[-1].redirects += [Redir(sys.stdin, "r", Text(self.multi_line_input))]
                self.do_show()
                self.multi_line_input = ''
                self.end_symbol = None
            else:
                self.multi_line_input += cmd
        else:
            cmd = self.store + cmd
            if cmd[-1] == '\\':
                self.store = self.store + cmd
                return
            args = []
            for g in re.finditer(r'"((\\.|[^"\\])*)"|\'((\\.|[^\'\\])*)\'|&&|\|\||<<|>>|#.*|([ \t]+)|[\w\.-]+|\$\w+|\$\{\w+\}|\$\(\(?|\[\[|\]\]|&\d+|\\.|.|\n', cmd.strip()):
                item = g.group(0)
                if item == '':
                    pass
                elif re.match(r'^\s*#', item):
                    pass
                elif g.group(1) is not None:
                    args += [Quote(g.group(1),True)]
                elif g.group(3) is not None:
                    args += [Quote(g.group(3),False)]
                elif g.group(5) is not None:
                    args += [Space(g.group(5))]
                else:
                    args += [item]
            self.assemble(args)
            if len(self.lines) > 0 and self.lines[-1].end_symbol is None:
                self.do_show()
    def do_show(self):
        for line in self.lines[self.show:]:
            line.trim()
        for line in self.lines[self.show:]:
            #print(line)
            line.pr()
        self.show = len(self.lines)

args = sys.argv[1:]
vartable["0"] = sys.argv[0]
shell = Shell()
for i in range(len(args)):
    a = args[i]
    with open(a,"r") as fd:
        #vartable["*"] = " ".join(args[i+1:])
        for line in fd.readlines():
            print()
            print("LINE:",line.strip())
            shell.process_input(line)
        break
