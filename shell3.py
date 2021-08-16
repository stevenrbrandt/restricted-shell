#!/usr/bin/env python3 
from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE, STDOUT, call
import os
import sys
import re
import io
from traceback import print_exc
if sys.stdout.isatty():
    from termcolor import colored
else:
    def colored(a,_):
        return a

def here(*args):
    import inspect
    stack = inspect.stack()
    frame = stack[1]
    print(colored("HERE:","blue"),"%s:%d" % (frame.filename, frame.lineno), *args, flush=True)
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

class Var:
    def __init__(self,s):
        self.s = s
    def __repr__(self):
        return '${'+self.s+'}'

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
        self.env = {}
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

    def find_env(self):
        i = 0
        lhs = None
        rhs = []
        spaces = 0
        while i+1 < len(self.args):
            if self.args[i+1] == '=' and type(self.args[i]) == str:
                lhs = self.args[i]
                i += 1
                while i < len(self.args):
                    if isinstance(self.args[i],Space):
                        if lhs is not None:
                            self.env[lhs] = rhs[1:]
                            lhs = None
                            rhs = []
                            break
                    else:
                        rhs += [self.args[i]]
                    i += 1
            else:
                break
            i += 1
        self.args = self.args[i:]
        if len(self.env)==0 and len(self.args)==0 and lhs is not None:
            self.args = [lhs]+rhs
            self.type = "set"
            self.env = {}
        elif lhs is not None:
            assert False

    def trim(self):
        self.find_redirects()
        self.trimmed = True
        while len(self.args) > 0 and isinstance(self.args[0],Space):
            self.args = self.args[1:]
        while len(self.args) > 0 and isinstance(self.args[-1],Space):
            self.args = self.args[:-1]
        self.find_env()

    def find_redirects(self):
        i = 0
        nargs = []
        while i < len(self.args):
            arg = self.args[i]
            if arg == "<" and self.type == "test2":
                nargs += [arg]
            elif arg in ["<", ">", ">>", "1>", "&>", ">&"]:
                post = 1
                post_fd = []
                if i+post < len(self.args) and isinstance(self.args[i+post],Space):
                    post += 1
                while i+post < len(self.args) and not isinstance(self.args[i+post],Space):
                    post_fd += [self.args[i+post]]
                    post += 1
                redir = Redir(None, arg, "".join(post_fd))
                self.redirects += [redir]
                i += post
            elif arg == "2>&1":
                redir = Redir(2,">",1)
                self.redirects += [redir]
            elif arg in ["1>&2", ">&2"]:
                redir = Redir(1,">",2)
                self.redirects += [redir]
            else:
                nargs += [arg]
            i += 1
        self.args = nargs

    def pr(self,indent=0):
        if self.trimmed:
            tr = "*"
        else:
            tr = ""
        print(" "*indent,"Command",tr,":",sep='')
        if len(self.env) > 0:
            print(" "*(indent+2),"Env: ",self.env,sep='')
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
        if self.end is not None and self.end != '\n':
            print(" "*(indent+2),"end: ",self.end,sep='')
        print(" "*indent,"]",sep='',end='')
        if indent==0:
            print()

    def __repr__(self):
        s = "Command(type="+self.type+",args="+str(self.args)
        if self.end is not None and self.end != '\n':
            ",end="+str(self.end)
        if self.end_symbol is not None:
            s += f",end_symbol={self.end_symbol}"
        if len(self.redirects)>0:
            s += ",redirects="+str(self.redirects)
        s += ")"
        return s

class Shell:
    def __init__(self):
        self.lines = []
        self.program = []
        self.store = ''
        self.show = 0
        self.end_symbol = None
        self.multi_line_input = ""
        self.vars = {}
        self.exports = {}
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def create_file(self, fname):
        here("creating file:",fname)
        return open(fname, "w")

    def read_file(self, fname):
        here("reading file:",fname)
        return open(fname, "r")

    def run(self, cmd, redirs=[]):
        if len(cmd) == 0:
            return "", "", -1
        if len(cmd[0]) == 0:
            return "", "", -1
        if cmd[0] in ["if", "then", "fi"]:
            return "", "", -1
        here("run:",cmd)
        sout = self.stdout
        serr = self.stderr
        sin = PIPE
        for r in redirs:
            if r.fd_orig is None and r.mode == '>':
                sout = self.create_file(r.fd_new)
            elif r.fd_orig == 2 and r.mode == '>' and r.fd_new == 1:
                serr = sout
            elif r.fd_orig == 1 and r.mode == '>' and r.fd_new == 2:
                here()
                sout = serr
            elif r.fd_orig is None and r.mode == '<':
                sin = self.read_file(r.fd_new)
            else:
                here(r)
                raise Exception()
        here(cmd)
        p = Popen(cmd, stdin=sin, stdout=sout, stderr=serr, universal_newlines=True)
        p.communicate("")
        return p.returncode

    def execute(self, cmd):
        if cmd.type == "set":
            s = ''
            for a in cmd.args[2:]:
                if isinstance(a,Command):
                    s += self.execute(a)
                else:
                    s += str(a)
            self.vars[cmd.args[0]] = s
        elif cmd.type == "calc":
            return eval(" ".join(cmd.args))
        elif cmd.type in ["exec", "evalproc"]:
            if cmd.type == "evalproc":
                sav = self.stdout
                tmpfile = f"/tmp/tmp.{os.getpid()}.txt"
                stio = open(tmpfile, "w")
                self.stdout = stio
            nargs = [""]
            for a in cmd.args:
                if isinstance(a,Command):
                    nargs[-1] += str(self.execute(a))
                elif isinstance(a,Space):
                    nargs += [""]
                elif isinstance(a,Var):
                    if a.s in self.vars:
                        nargs[-1] += self.vars[a.s]
                else:
                    nargs[-1] += str(a)
            rc = self.run(nargs, cmd.redirects)
            if cmd.type == "evalproc":
                stio.close()
                if self.stdout == stio:
                    self.stdout = sav
                with open(tmpfile,"r") as fd:
                    rv = fd.read().strip()
                    here("rv:",rv)
                    return rv
        return ''

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
                self.show = len(self.lines)-1
                self.do_show()
                self.multi_line_input = ''
                self.end_symbol = None
            else:
                self.multi_line_input += cmd
        else:
            cmd = self.store + cmd
            g = re.search(r'\\(\r\n|\n|\r|)$',cmd)
            if g:
                self.store = self.store + cmd[:g.start()]
                return
            args = []
            for g in re.finditer(r'"((\\.|[^"\\])*)"|\'((\\.|[^\'\\])*)\'|&&|\|\||<<|>>|<&|&<|\d?>(?:&\d|)|#.*|([ \t]+)|[\w\.-]+|\$(\w+)|\$\{(\w+)\}|\$\(\(?|\[\[|\]\]|\\.|.|\n', cmd.strip()):
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
                elif g.group(6) is not None:
                    args += [Var(g.group(6))]
                elif g.group(7) is not None:
                    args += [Var(g.group(7))]
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
            self.execute(line)
        self.show = len(self.lines)

args = sys.argv[1:]
vartable["0"] = sys.argv[0]
shell = Shell()
shell.stdout = open("out.txt", "w")
shell.stderr = open("err.txt", "w")
for i in range(len(args)):
    a = args[i]
    with open(a,"r") as fd:
        #vartable["*"] = " ".join(args[i+1:])
        for line in fd.readlines():
            print()
            print("LINE:",line.strip())
            print("LINE:",line.strip(),file=shell.stdout,flush=True)
            print("LINE:",line.strip(),file=shell.stderr,flush=True)
            shell.process_input(line)
        break
