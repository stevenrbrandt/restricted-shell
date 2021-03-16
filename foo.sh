AGAVE_LOG_FILE=agave.log
set +x
if [ -e /etc/group ]
then echo it is true
else echo it is false
fi

# A comment
echo FOO IS RUNNING
echo 'FOO IS RUNNING';
date
function x() {
    echo x
}
function y() {
    echo 'y';
}
echo ERR >&2
echo Fisk $(date) 2>&1 > x.log
sh -c ./foo2.sh
