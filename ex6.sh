if [ -r /etc/group ]
then echo foo
echo group exists
fi
if [ -r /etc/groupx ]
then echo groupx exists
echo foo
else echo groupx DOES NOT exist
fi

if bash ./a.sh && bash ./b.sh
then
echo and does not work
else
echo and works 1
fi

if bash ./b.sh && bash ./a.sh
then
echo and does not work
else
echo and works 2
fi

if bash ./b.sh && bash ./b.sh
then
echo and does not work
else
echo and works 3
fi

if bash ./a.sh && bash ./a.sh
then
echo and works 4
else
echo and does not work
fi

if [ 1 = 1 ]
then
    if [ 1 = 2 ]
    then
        echo fail
    else
        echo succeed
    fi
else
    echo fail
fi

if bash ./a.sh || bash ./b.sh
then
echo or works 1
else
echo or does not work
fi

if bash ./b.sh || bash ./a.sh
then
echo or works 2
else
echo or does not work
fi

if bash ./b.sh || bash ./b.sh
then
echo or does not work
else
echo or works 3
fi

if bash ./a.sh && bash ./a.sh
then
echo or works 4
else
echo or does not work
fi
