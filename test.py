for txt in [
        'echo A',
        'echo A & && echo B',
        'echo A && echo B',
        'echo A && echo B & ',
        'echo A &',
        'echo $HOME >> test.log',
        'echo $(date) >> err.log',
        'Aa="x"echo "hi"',
        'Aa="x"echo hi',
        'Aa="x"echo hi$(echo hi)',
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
        'echo X 2>/dev/null',
        '',
        '''function foo() {
            echo bar
        }''',
        'AGAVE_FOO=bar',
        'echo "AGAVE_FOO=${AGAVE_FOO}" >&2',
        'echo "AGAVE_FOO=${AGAVE_FOO}"'
        ]:
    m = Matcher(*pp, txt)
    if m.matches():
        print(colored(txt,"cyan"))
        #print(colored(m.gr.dump(),"magenta"))
        run_shell(m.gr)
    else:
        m.showError()
        break
