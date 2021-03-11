from Piraha import parse_peg_src, Matcher
from subprocess import Popen, PIPE
import os
import sys

verbose = True

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
pidtable = {}

def do_redir(g):
    redir_fd = 1
    out_fds = [PIPE, PIPE]
    ind = 0
    if g.groupCount() == 3:
        if g.group(0).getPatternName() == "fd":
            ind = 1
            redir_fd = int(g.group(0).substring())
    if g.groupCount() == 2+ind:
        if g.group(ind).getPatternName() == "op" and g.group(ind+1).group(0).getPatternName() == "fname":
            op = g.group(ind).substring()
            fname = os.path.realpath(g.group(ind+1).substring())
            if fname.endswith(".log") or fname == "/dev/null":
                if op == ">":
                    if verbose:
                        print("Open '%s' for write." % fname)
                    try:
                        out_fds[redir_fd-1] = open(fname,"w")
                        return out_fds
                    except:
                        if verbose:
                            print(colored("Write failed","red"))
                        return PIPE
                elif op == ">>":
                    if verbose:
                        print("Open '%s' for append." % fname)
                    try:
                        out_fds[redir_fd-1] = open(fname,"a")
                        return out_fds
                    except:
                        if verbose:
                            print(colored("Append failed","red"))
                        return out_fds
            else:
                if verbose:
                    print("Open for: '%s' is denied." % fname)
                return out_fds

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
    p  = g.getPatternName()
    if p in ["cmd0", "expr"]:
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
            enval = arg_eval(e.group(1))
            env[ename] = eval
                
        cmd = g.group(istart).substring()
        args = [cmd]
        background = False
        out_fd, err_fd = PIPE, PIPE
        for i in range(istart+1,g.groupCount()):
            if g.group(i).getPatternName() == "redir":
                out_fd, err_fd = do_redir(g.group(i))
            elif g.group(i).getPatternName() == "background":
                background = True
            else:
                args += [arg_eval(g.group(i))]
        if args[0] == "cd":
            env["PWD"] = args[1]
        else:
            if args[0] == "sh":
                args = ["echo"]+args
            dir = env.get("PWD",os.getcwd())
            if not os.path.exists(dir):
                dir = os.getcwd()
            if verbose:
                print(colored(args,"yellow"))
            p = Popen(args, cwd=dir, stdout=out_fd, stderr=err_fd, universal_newlines=True)
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

                # This will be true for a file redirect
                if o is None:
                    o = ""
                if e is None:
                    e = ""

                env["?"] = str(p.returncode)
                if show_output:
                    print(o)
                    if e.strip() != "":
                        print(colored(e,"red"))
                return o.strip()
    elif p == "join":
        return ""
    elif p == "redir":
        return ""
    else:
        raise Exception(g.getPatternName())

grammar = r"""
skipper=\b(\n\\|[ \t])*
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
cmd=({env} )*({name})( ({redir}|{arg}))*( {background}|)
join=;|\|\||&&
fd=[0-2]
out={fname}|&{fd}
op=>>?
redir=({fd}|) {op} {out}
expr={cmd}( {-join} {cmd})*
cmd0=^ {expr} $
"""
pp = parse_peg_src(grammar)
for txt in [
        'echo A & && echo B',
        'echo A && echo B',
        'echo A && echo B & ',
        'echo A &',
        'echo $HOME >> test.log',
        'echo $(date) >> err.log',
        'A="x"echo "hi"',
        'A="x"echo hi',
        'A="x"echo hi$(echo hi)',
        'chmod +x hello-world-kfqib6kiraeixqifue6k.ipcexe',
        'echo 1;echo 2;echo 3',
        'echo 1>/x ;echo 2;echo 3',
        r'''echo >> /work/.agave.log  ;cd /work/sbrandt''',
        r'''printf "[%s] %b\n" $(date '+%Y-%m-%dT%H:%M:%S%z') "$(echo 'No startup script defined. Skipping...')" >> /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k/.agave.log  ;cd /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k''',
        'echo "---END---;PROCESS=1615414985396;EXITCODE=$?"echo "---BEGIN---"',
        'echo >> /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k/.agave.log',
        ' cd /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k',
        r'''printf "[%s] %b\n" $(date '+%Y-%m-%dT%H:%M:%S%z') "$(echo 'No startup script defined. Skipping...')"''',
        r'''printf "[%s] %b\n" $(date '+%Y-%m-%dT%H:%M:%S%z')"$(echo 'No startup script defined. Skipping...')"''',
        r''' echo "---BEGIN---"; uname; echo "---END---;PROCESS=1615414985396;EXITCODE=$?"''',
        r'''echo "---BEGIN---"; printf "[%s] %b\n" $(date '+%Y-%m-%dT%H:%M:%S%z') "$(echo 'No startup script defined. Skipping...')" >> /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k/.agave.log  ;  cd /work/sbrandt/tg457049/job-1a56a844-b144-4866-b554-17cbb5b922e7-007-hello-world-kfqib6kiraeixqifue6k &&  chmod +x hello-world-kfqib6kiraeixqifue6k.ipcexe > /dev/null  &&  sh -c './hello-world-kfqib6kiraeixqifue6k.ipcexe 2> hello-world-kfqib6kiraeixqifue6k.err 1> hello-world-kfqib6kiraeixqifue6k.out &  export AGAVE_PID=$! &&  if [ -n "$(ps -o comm= -p $AGAVE_PID)" ] || [ -e hello-world-kfqib6kiraeixqifue6k.pid ]; then  echo $AGAVE_PID;  else  cat hello-world-kfqib6kiraeixqifue6k.err;  fi'; echo "---END---;PROCESS=1615414985415;EXITCODE=$?"''',
        "echo $(date '+%Y-%m-%dT%H:%M:%S%z')",
        "date '+%Y-%m-%dT%H:%M:%S%z'",
        'echo X 2>/dev/null'
        ]:
    m = Matcher(*pp, txt)
    if m.matches():
        print(colored(txt,"cyan"))
        print(colored(m.gr.dump(),"magenta"))
        run_shell(m.gr)
    else:
        m.showError()
        break
