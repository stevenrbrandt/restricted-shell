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

if [ false ] && [ false ]
then
echo and works 3
else
echo and does not work
fi
