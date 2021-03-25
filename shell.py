#!/usr/bin/env python3 
from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE, STDOUT
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

functable = {}
pidtable = {}

def Done():
    for p in pidtable:
        o, e = pidtable[p].communicate()
        print(o,e)
    if "?" in env:
        rc = int(env["?"])
    else:
        rc = 0
    exit(rc)

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
            if re.match(r'^.*\.(out|err|log)$',fname) or fname == "/dev/null":
                if op == ">":
                    if verbose:
                        print("Open '%s' for write." % fname)
                    try:
                        out_fds[redir_fd-1] = open(fname,"a")
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
    print("FAIL:",g.dump())
    Done()

def arg_eval(g):
    p  = g.getPatternName()
    arg_str = ""
    if p in ["arg", "dquote"]:
        for i in range(g.groupCount()):
            arg_str += arg_eval(g.group(i))
        return arg_str
    elif p in ["char", "fname", "squote", "startsquare", "endsquare", "argstr"]:
        return g.substring()
    elif p == "shell":
        r = run_shell(g.group(0),show_output=False)
        assert r is not None, g.dump()
        return r
    elif p == "var":
        if g.substring() == "$?":
            return env["?"]
        elif g.substring() == "$!":
            return env.get("!","0")
        elif g.substring() == "$$":
            return str(os.getpid())
        elif g.groupCount() == 1 and g.group(0).getPatternName() == "name":
            name = g.group(0).substring()
            if name in env:
                return env[name]
            elif name in os.environ:
                return os.environ[name]
            else:
                return ""
        else:
            raise Exception(g.substring())
    raise Exception(g.getPatternName())

def eval_truth(g):
    p  = g.getPatternName()
    if p == "truth":
        if g.groupCount() == 1:
            return eval_truth(g.group(0))
        elif g.groupCount() == 3:
            t1 = eval_truth(g.group(0))
            binop = g.group(1).substring()
            t2 = eval_truth(g.group(2))
            if binop == "&&":
                return t1 and t2
            else:
                return t1 or t2
    elif p == "test":
        assert g.group(0).getPatternName() == "fflag"
        fflag = g.group(0).substring()
        arg = arg_eval(g.group(1))
        if fflag == "e":
            fname = os.path.realpath(arg)
            return os.path.exists(fname)
        elif fflag == "n":
            return len(arg) != 0
        elif fflag == "z":
            return len(arg) == 0
    print("FAIL:",g.dump())
    Done()

def safe(args):
    return args

def chk_chmod(args):
    assert args[1] == "+x"
    assert re.match(r'^.*\.ipcexe$', args[2])
    return args

def chk_access(args):
    for k in args[1:]:
        k = os.path.realpath(k)
        if os.path.exists(k):
            # Only cat publicly readable files
            assert os.stat(k).st_mode & 0o400 == 0o400, "Illegal access to '%s'" % k
        d = os.path.dirname(k)
        if os.path.exists(d):
            assert os.stat(d).st_mode & 0o500 == 0o500, "Illegal access to '%s'" % k
        # block anything in the .ssh directory
        assert "/.ssh/" not in k, "Illegal access to '%s'" % k
        # Can't read/write to the exe dir
        assert not d.starswith(exe_dir), "Illegal access to '%s'" % k
        # Can't read/write to the home dir
        assert d != home, "Illegal access to '%s'" % k
        # No bashrc and possibly other things
        # Actually, that should be blocked by
        # restricting access to the home dir.
        assert os.path.basename(k) not in [".bashrc"], "Illegal access to '%s'" % k
        # block anything in /etc
        assert not k.startswith("/etc"), "Illegal access to '%s'" % k
    return args

def new_sftp(args):
    assert sftp_alt is not None, "Please set environment variable SFTP"
    print("Exec:",sftp_alt,file=log_fd)
    os.execv(sftp_alt,[sftp_alt])

def chk_sbatch(args):
    # Force batch files to execute using shell.py
    src_file = os.path.realpath(args[1]) 
    with open(src_file, "r") as ffd:
        src_content = ffd.read()
    alt_file = src_file + ".sh"
    with open(alt_file, "w") as ffd:
        print("#!", my_shell, sep='', file=ffd)
        print(src_content, file=ffd, end='')
    return [args[0], alt_file]

def chk_set(args):
    global verbose
    assert args[1] in ["+x","-x"]
    if args[1] == "-x":
        verbose = True
    elif args[1] == "+x":
        verbose = False
    return ["true"]

def chk_sh(args):
    if short_circuit:
        return ["true"]
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
            try:
                sys.stdout.flush()
                sys.stderr.flush()
                save_out = sys.stdout
                save_err = sys.stderr
                save_dir = os.getcwd()
                try:
                    run_text(a)
                except ExitShell as e:
                    print("Caught")
                    if env["?"] == 0:
                        return ["true"]
                    else:
                        return ["false"]
            finally:
                sys.stdout.flush()
                sys.stdout = save_out
                sys.stderr.flush()
                sys.stderr = save_err
                os.chdir(save_dir)
    if len(safe) > 0 and len(unsafe) > 0:
        raise Exception("Mixture of safe and unsafe scripts")
    elif len(safe) == 0 and len(unsafe) > 0:
        #for script in unsafe:
        #    out = run_script(script)
        #return out
        args = [sys.executable,my_shell]+unsafe
        for u in unsafe:
            try:
                run_script(u)
            except ExitShell:
                pass
        if env.get("?","1") == "0":
            return ["true"]
        else:
            if len(if_stack)>0 and if_stack[-1] == 0:
                if_stack[-1] += 1
            return ["false"]
    elif len(safe)==0 and len(unsafe)==0:
        return ["false"]
    else:
        raise Exception()

def do_exit(args):
    if len(args) > 0:
        env["?"] = args[1]
    else:
        env["?"] = "0"
    raise ExitShell(env["?"])

commands = {
    "sleep" : safe,
    "date" : safe,
    "echo" : safe,
    "ps" : safe,
    "true" : safe,
    "false" : safe,
    "sacct" : safe,
    "printf" : safe,
    "uname" : safe,
    "chmod" : chk_chmod,
    "cat" : chk_access,
    "cp" : chk_access,
    "if" : safe,
    "then" : safe,
    "else" : safe,
    "fi" : safe,
    "set" : chk_set,
    "[" : safe,
    "exec" : safe,
    sftp : new_sftp,
    "sbatch" : chk_sbatch,
    "sh" : chk_sh,
    "bash" : chk_sh,
    "exit" : do_exit,
}

def run_cmd(args, out_fds, background,show_output):
    global verbose, if_stack
    out_fd, err_fd, dest = out_fds
    assert args[0] in commands, "Illegal command '%s'" % args[0]
    args = commands[args[0]](args)
    if args[0] == "if":
        if_stack += [-1]
        run_cmd(args[1:], out_fds, background, show_output)
        if_stack[-1] = int(env["?"])
        return ""
    elif args[0] == "exec":
        pass
    elif args[0] == "then":
        assert if_stack[-1] in [0,1], "then without if"
        if_stack[-1] += 2
        args = args[1:]
        if len(args) == 0:
            return ""
        assert args[0] in commands, "Illegal command '%s'" % args[0]
        args = commands[args[0]](args)
    elif args[0] == "else":
        assert if_stack[-1] in [2,3], "else without then"
        if_stack[-1] += 2
        args = args[1:]
        if len(args) == 0:
            return ""
        assert args[0] in commands, "Illegal command '%s'" % args[0]
        args = commands[args[0]](args)
    elif args[0] == "fi":
        assert if_stack[-1] in [2,3,4,5], "fi without if"
        if_stack = if_stack[:-1]
        return ""
    if len(if_stack)>0 and if_stack[-1] in [3,4]:
        # state 3 means we're inside "then" but the test for "if" failed
        # state 4 means we're inside "else" but the test for "if" succeeded
        return ""
    if args[0] == "true":
        env["?"]="0"
        return "0"
    if args[0] == "false":
        env["?"]="1"
        return "1"
                    
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
    if short_circuit:
        return ""
    if args[0] == "exec":
        # Not sure if this makes sense to do
        if type(out_fd).__name__ == "TextIOWrapper":
            sys.stdout.flush()
            sys.stdout = out_fd
        if type(err_fd).__name__ == "TextIOWrapper":
            sys.stderr.flush()
            sys.stderr = err_fd
        return
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
        if len(if_stack) > 0 and if_stack[-1] in [-1,0,1]:
            if env["?"] == "0":
                if_stack[-1] = 0
            else:
                if_stack[-1] = 1
            #print("set if_stack:",if_stack[-1],"<-",args,p.returncode)
        if args[0] == "[":
            if_stack[-1] = int(env["?"])
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
    return ""

def run_shell(g,background=False,show_output=True):
    assert type(show_output)==bool
    assert type(background)==bool
    global verbose, if_stack, short_circuit
    p  = g.getPatternName()
    if p in ["cmd0", "expr", "all", "lines"]:
        for i in range(g.groupCount()):
            run_shell(g.group(i))
    elif p == "line":
        bg = False
        if g.groupCount()==2:
            if g.group(1).group(0).substring() == "&":
                bg = True
        run_shell(g.group(0), bg, show_output)
        if g.groupCount()==2:
            run_shell(g.group(1), bg, show_output)
    elif p in ["shell"]:
        return run_shell(g.group(0),background=background)
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
                
        cmd = arg_eval(g.group(istart))
        args = [cmd]
        out_fds[0] = PIPE
        out_fds[1] = PIPE
        out_fds[2] = "1"
        for i in range(istart+1,g.groupCount()):
            if g.group(i).getPatternName() == "redir":
                do_redir(g.group(i))
            elif g.group(i).getPatternName() == "eol" and g.group(i).group(0).substring()=="&":
                background = True
            else:
                args += [arg_eval(g.group(i))]
        out_fd, err_fd, dest = out_fds
        if args[0] == "cd":
            cwd = os.path.realpath(args[1])
            hpat = re.sub(r'/*$','',os.environ["HOME"]) + '/[\w\.-]+'
            wpat = '/work/'
            if re.match(hpat, cwd) or re.match(wpat, cwd):
                env["PWD"] = cwd
                os.chdir(cwd)
            else:
                assert False, "Bad directory for cd: '%s'" % cwd
        else:
            return run_cmd(args, out_fds, background, show_output)
    elif p == "join":
        return ""
    elif p == "redir":
        return ""
    elif p == "func":
        # At present, functions are parsed, not executed
        # Maybe that's all we'll ever do with them.
        fname = g.group(0).substring()
        functable[fname] = g
    elif p in ["setenv", "export"]:
        ename = g.group(0).substring()
        check_ename(ename)
        enval = arg_eval(g.group(1))
        env[ename] = enval
    elif p in ["eol"]:
        endtok = g.group(0).substring()
        lastcode = 0
        if "?" in env and env["?"] != "0":
            lastcode = 1
        if lastcode == 0 and endtok == "||":
            short_circuit = True
        elif lastcode != 0 and endtok == "&&":
            short_circuit = True
        else:
            short_circuit = False
    elif p == "if":
        print("if")
        if eval_truth(g.group(0)):
            if_stack += [0]
        else:
            if_stack += [1]
    elif p == "comment":
        pass
    else:
        raise Exception(g.getPatternName())

grammar = r"""
skipper=\b[ \t]*
shell=\$\( {cmd} \)
name=[a-zA-Z][a-zA-Z0-9_-]*
fname=[+/a-zA-Z0-9_\.-]+|\[
argstr=[=+/a-zA-Z0-9_\.-]+|\[
var=\$(\{{name}\}|{name}|[?!$])
quoteelem={var}|{shell}|{char}
char=\\.|[^"]
dquote={-quoteelem}*
squote=(\\.|[^'])*
endsquare=\]
startsquare=\[
flag=-[a-z]
arg=("{dquote}"|'{squote}'|{argstr}|{var}|{shell}|{startsquare}|{endsquare}|{flag})
env={name}={arg}
blank=[ \t]*
binop = &&|\|\|
export=export {name}={arg}
setenv={name}={arg}
fd=[0-2]
out={arg}|&{fd}
op=>>?
redir=(({fd}|) {op} {out}|{fd} {op} ({out}|))
s=[ \t\r\n]*
func=function {name} \( \) \{ (\n )?({line} )*[\n\r\t ]*\} ({redir}|)*
eol=(\#[^\n]*|){endtok}
endtok=([\n;]+|&&?|\|\||$)
all=^{lines}$
cmd=({env} )*{arg}( ({redir}|{arg}))*
comment=\#[^\n]*[ \t\r\n]*
line=({comment}|({func}|{export}|{cmd}|{setenv}) {eol})
lines=^( {line})+$
"""
pp = parse_peg_src(grammar)

def run_text(txt):
    m = Matcher(*pp, txt)
    if m.matches():
        if verbose:
            print(colored(txt,"cyan"))
        #print(colored(m.gr.dump(),"magenta"))
        run_shell(m.gr)
    else:
        m.showError()
        m.showError(sys.stderr)
        raise Exception("syntax error")

stack = []
def run_script(fname):
    global stack
    fname = os.path.realpath(fname)
    #assert fname not in stack, "No recursion"
    assert len(stack) < 20, "Recursion limit exceeded"
    stack += [fname]
    with open(fname,"r") as fd:
        txt = fd.read()
    run_text(txt)
    stack = stack[:-1]

done = False
for f in sys.argv[1:]:
    if f == "-c":
        continue
    try:
        run_script(f)
    except ExitShell:
        pass
    done = True
if done:
    Done()

def run_text_check(txt):
    if txt.strip() == "":
        return ""
    try:
        r = run_text(txt)
        print("Succeeded for text:",txt,file=log_fd)
        return r
    except ExitShell as e:
        Done()
    except:
        if sys.stdout.isatty():
            print("Failed for text:",txt)
            print_exc()
        else:
            print("Failed for text:",txt,file=log_fd)
            print_exc(file=log_fd)

def main():
    ssh_cmd = os.environ.get("SSH_ORIGINAL_COMMAND","").strip()
    if ssh_cmd != "":
        run_text_check(ssh_cmd)
        Done()

    while True:
        try:
            if sys.stdout.isatty():
                print("$ ",end='',flush=True)
            line = input()
        except EOFError:
            Done()
        run_text_check(line)
    Done()

if __name__ == "__main__":
    main()
