from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE, STDOUT
import os
import sys
import re

verbose = False

exe_dir = os.environ.get("EXE_DIR",os.path.join(os.environ["HOME"],"exe"))

functable = {}

def check_ename(name):
    if name.startswith("AGAVE_"):
        return
    if re.match(r'[A-Z0-9_]+$', name):
        raise Exception("Cannot set '%s'" % name)

if sys.stdout.isatty():
    try:
        from termcolor import colored
    except:
        def colored(txt,_):
            return txt
else:
    def colored(txt,_):
        return txt

env = {}
for nm in ["USER", "HOME", "PATH", "PYTHONPATH", "LD_LIBRARY_PATH"]:
    env[nm]=os.environ.get(nm,"")
pidtable = {}

out_fds = [PIPE, PIPE, "1"]

def do_redir(g):
    redir_fd = 1
    ind = 0
    if g.groupCount() == 3:
        if g.group(0).getPatternName() == "fd":
            ind = 1
            redir_fd = int(g.group(0).substring())
    if g.groupCount() == 2+ind:
        if g.group(ind).getPatternName() == "op" and g.group(ind+1).group(0).getPatternName() == "fd":
            dest = g.group(ind+1).group(0).substring() 
            if dest == "2":
                out_fds[1] = STDOUT
                out_fds[2] = "2"
                return
            elif dest == "1":
                out_fds[1] = STDOUT
                out_fds[2] = "1"
                return
            else:
                assert False
        elif g.group(ind).getPatternName() == "op" and g.group(ind+1).group(0).getPatternName() == "arg":
            op = g.group(ind).substring()
            fname = os.path.realpath(g.group(ind+1).substring())
            if fname.endswith(".log") or fname == "/dev/null":
                if op == ">":
                    if verbose:
                        print("Open '%s' for write." % fname)
                    try:
                        out_fds[redir_fd-1] = open(fname,"w")
                        return
                    except:
                        if verbose:
                            print(colored("Write failed","red"))
                        return
                elif op == ">>":
                    if verbose:
                        print("Open '%s' for append." % fname)
                    try:
                        out_fds[redir_fd-1] = open(fname,"a")
                        return
                    except:
                        if verbose:
                            print(colored("Append failed","red"))
                        return
            else:
                if verbose:
                    print("Open for: '%s' is denied." % fname)
                return

    # Failure case
    print(g.dump())
    exit(0)

def arg_eval(g):
    p  = g.getPatternName()
    arg_str = ""
    if p in ["arg", "dquote"]:
        for i in range(g.groupCount()):
            arg_str += arg_eval(g.group(i))
        return arg_str
    elif p in ["char", "fname", "squote"]:
        return g.substring()
    elif p == "shell":
        return run_shell(g.group(0),show_output=False)
    elif p == "var":
        if g.substring() == "$?":
            return env["?"]
        elif g.groupCount() == 1 and g.group(0).getPatternName() == "name":
            name = g.group(0).substring()
            if name in env:
                return env[name]
            elif name in os.environ:
                return os.environ[name]
            else:
                return ""
    raise Exception(g.getPatternName())

def run_shell(g,show_output=True):
    global verbose
    p  = g.getPatternName()
    if p in ["cmd0", "expr", "all", "line", "lines"]:
        for i in range(g.groupCount()):
            run_shell(g.group(i))
    elif p in ["shell"]:
        return run_shell(g.group(0))
    elif p in ["cmd"]:
        istart = 0
        while True:
            e = g.group(istart)
            if e.getPatternName() != "env":
                break
            istart += 1
            ename = e.group(0).substring()
            check_ename(ename)
            enval = arg_eval(e.group(1))
            env[ename] = enval
                
        cmd = g.group(istart).substring()
        args = [cmd]
        background = False
        out_fds[0] = PIPE
        out_fds[1] = PIPE
        out_fds[2] = "1"
        for i in range(istart+1,g.groupCount()):
            if g.group(i).getPatternName() == "redir":
                do_redir(g.group(i))
            elif g.group(i).getPatternName() == "background":
                background = True
            else:
                args += [arg_eval(g.group(i))]
        out_fd, err_fd, dest = out_fds
        if args[0] == "cd":
            env["PWD"] = args[1]
        else:
            if args[0] not in ["date", "echo", "sleep", "chmod", "sh", "ls", "set"]:
                raise Exception("Illegal command '%s'" % args[0])
            if args[0] == "set":
                assert args[1] in ["+x","-x"]
                if args[1] == "+x":
                    verbose = True
                elif args[1] == "-x":
                    verbose = False
                return
            if args[0] == "chmod":
                assert args[1] == "+x"
                assert re.match(r'^.*\.ipcexe$', args[2])
            if args[0] == "sh":
                safe = []
                unsafe = []
                minus_c = False
                for a in args[1:]:
                    if a == "-c":
                        minus_c = True
                    elif os.path.exists(a):
                        fpath = os.path.realpath(a)
                        if a.startswith(exe_dir):
                            safe += [a]
                        else:
                            unsafe += [a]
                    else:
                        assert False, "Bad argument to sh '%s'" % a
                if len(safe) > 0 and len(unsafe) > 0:
                    raise Exception("Mixture of safe and unsafe scripts")
                if len(safe) == 0 and len(unsafe) > 0:
                    for script in unsafe:
                        run_script(script)
                    return
                            
            dir = env.get("PWD",os.getcwd())
            if not os.path.exists(dir):
                dir = os.getcwd()
                os.chdir(dir)
            if verbose:
                print(colored(args,"yellow"))
            my_env = os.environ.copy()
            for k in env:
                if re.match(r'^\w+$', k):
                    my_env[k] = env[k]
            p = Popen(args, env=my_env, cwd=dir, stdout=out_fd, stderr=err_fd, universal_newlines=True)
            if background:
                pidtable[str(p.pid)] = p
                if "!" in env:
                    pidstr = env["!"]
                    if verbose:
                        print(colored("waiting","green"),pidstr)
                    if pidstr in pidtable:
                        o2, e2 = pidtable[pidstr].communicate()
                        del pidtable[pidstr]
                        if e2.strip() != "":
                            if verbose:
                                print(colored("child error:","red"),e2)
                env["!"] = str(p.pid)
            else:
                o, e = p.communicate()

                # Redirect to stderr
                if out_fd == PIPE and err_fd == STDOUT:
                    if dest == "2":
                        e = o
                        o = ""
                    elif dest == "1":
                        o = e
                        e = ""

                # This will be true for a file redirect
                if o is None:
                    o = ""
                if e is None:
                    e = ""

                env["?"] = str(p.returncode)
                if show_output:
                    o = o.rstrip()
                    e = e.rstrip()
                    if o != "":
                        print(o)
                    if e != "":
                        if sys.stderr.isatty():
                            print(colored(e,"red"),file=sys.stderr)
                        else:
                            print(e,file=sys.stderr)
                return o
    elif p == "join":
        return ""
    elif p == "redir":
        return ""
    elif p == "func":
        # At present, functions are parsed, not executed
        # Maybe that's all we'll ever do with them.
        fname = g.group(0).substring()
        functable[fname] = g
    elif p == "setenv":
        ename = g.group(0).substring()
        check_ename(ename)
        enval = arg_eval(g.group(1))
        env[ename] = enval
    elif p in ["comment", "blank"]:
        pass
    else:
        raise Exception(g.getPatternName())

grammar = r"""
skipper=\b[ \t]*
shell=\$\( {cmd} \)
name=[a-zA-Z][a-zA-Z0-9_-]*
fname=[+/a-zA-Z0-9_\.-]+
var=\$(\{{name}\}|{name}|[?!])
quoteelem={var}|{shell}|{char}
char=\\.|[^"]
dquote={-quoteelem}*
squote=(\\.|[^'])*
arg=("{dquote}"|'{squote}'|{fname}|{var}|{shell})
env={name}={arg}
#background=&[ \t]
background=&(?!&)
comment=\#.*
blank=[ \t]*
cmd=({env} )*({name})( ({redir}|{arg}))*( {background}|)
export=export {name}={arg}
setenv={name}={arg}
join=;|\|\||&&
fd=[0-2]
out={arg}|&{fd}
op=>>?
redir=({fd}|) {op} {out}
expr={cmd}( {-join} {cmd})*( {join}|)
s=[ \t\r\n]*
func=function {name} \( \){-s}*\{{-s}{lines}{-s}\} ({redir}|)*
line=( ({comment}|{export}|{func}|{expr}|{setenv}|{blank}) (\n|$))
lines={line}*
all=^{lines}$
"""
pp = parse_peg_src(grammar)

already_ran = set()

def run_script(fname):
    fname = os.path.realpath(fname)
    assert fname not in already_ran, "Cannot re-run script '%s'" % fname
    already_ran.add(fname)
    with open(fname,"r") as fd:
        txt = fd.read()
    m = Matcher(*pp, txt)
    if m.matches():
        if verbose:
            print(colored(txt,"cyan"))
        #print(colored(m.gr.dump(),"magenta"))
        run_shell(m.gr)
    else:
        m.showError()
        raise Exception("syntax error")

for f in sys.argv[1:]:
    if f == "-c":
        continue
    run_script(f)
