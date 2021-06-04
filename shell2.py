#!/usr/bin/env python3 
from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE, STDOUT, call
import os
import sys
import re
from traceback import print_exc

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
program = []

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

def explode(item):
    s = ''
    pos = 0
    for g in re.finditer(r'\\\$|\${([^}]*)}|\$(\w+)|\$(.)', item):
        for k in g.groups():
            if k is not None:
                s += item[pos:g.start()]
                pos = g.end()
                s += vartable.get(k,"")
                break
    s += item[pos:]
    return s

def process_line(line,pc):
    global in_for, in_do, program, for_stack, vartable, in_if, if_stack
    #print(">>",pc,line)
    line = [explode(item) for item in line]
    if len(line) == 0:
        return
    if line[0] == "if":
        if_stack += [0]
        process_line(line[1:], pc)
        if_stack[-1] = vartable.get("?",1)
        return
    elif line[0] == "then":
        if if_stack[-1] == 0:
            process_line(line[1:], pc)
        return
    elif line[0] == "else":
        if if_stack[-1] == 0:
            if_stack[-1] = 1
        else:
            if_stack[-1] = 0
        if if_stack[-1] == 0:
            process_line(line[1:], pc)
        return
    elif line[0] == "fi":
        if_stack = if_stack[:-1]
        return

    if len(if_stack) > 0 and if_stack[-1] != 0:
        pass
    elif line[0] == "for":
        in_for = True
        vname = line[1]
        assert re.match(r'^[a-zA-Z_]', vname), 'vname = "%s"' % vname
        assert line[2] == "in"
        values = []
        for v in line[3:]:
            values += re.split(r'[ \t]+', v)
        for_stack += [{
            "vname":vname,
            "value_num":0,
            "pos":pc+1,
            "values":values
        }]
        vartable[vname] = values[0]
    elif line[0] == "do":
        in_do = True
        process_line(line[1:],pc)
        assert in_for, line
        # assert not in_do, line
    elif line[0] == "done":
        for_data = for_stack[-1]
        for v in for_data["values"][1:]:
            vartable[for_data["vname"]] = v
            in_do = False
            for p in range(for_data["pos"],pc):
                process_line(program[p],p)
        for_stack = for_stack[:-1]
    else:
        if len(line) > 0:
            if line[0] == "export":
                g = re.match(r'(\w+)=(.*)', line[1])
                assert g, line[1]
                vartable[g.group(1)]=g.group(2)
            elif re.search(r'=', line[0]):
                g = re.match(r'(\w+)=(.*)', line[0])
                assert g, line[0]
                vartable[g.group(1)]=g.group(2)
            else:
                output_stream = PIPE
                error_stream = PIPE
                input_stream = open("/dev/null","r")
                new_line = []
                i = 0
                while i < len(line):
                    item = line[i]
                    i += 1
                    if item == ">":
                        fname = line[i]
                        i += 1
                        output_stream = open(fname,"a+")
                    else:
                        new_line += [item]

                p = Popen(new_line, 
                    stdout=output_stream,
                    stderr=error_stream,
                    stdin=input_stream,
                    universal_newlines=True)
                out, err = p.communicate()
                if out is not None:
                    print(out, end='')
                if err is not None:
                    print(err, end='', file=sys.stderr)
                vartable["?"] = p.returncode
                #print(err, end='')

def process_input(input):
    global program
    lines = []
    line = []
    word = ""
    for g in re.finditer(r'"((\\.|[^"\\])*)"|\'((\\.|[^\'\\])*)\'|&&|\|\||\w+|.|\n', input.strip()):
        item = g.group(0)
        if g.group(1) is not None:
            word += unesc(g.group(1))
        elif g.group(3) is not None:
            word += unesc(g.group(3))
        elif item in [" ", "\t"]:
            if word != "":
                line += [word]
            word = ""
        elif item in ["&&", "&", "||", ";", "\n"]:
            if word != "":
                line += [word]
                #print("add word:",word)
                word = ''
            line += [item]
            lines += [line]
            line = []
        else:
            word += item
    if word != "":
        line += [word]
    if line != []:
        lines += [line]
    for pc in range(len(lines)):
        line = lines[pc]
        if line[-1] in ["\n", ";"]:
            line = line[:-1]
        program += [line]
        process_line(line,pc)

for a in sys.argv[1:]:
    with open(a,"r") as fd:
        process_input(fd.read())
