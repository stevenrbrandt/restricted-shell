if [ -r /etc/group ]
then
echo group exists
fi
if [ -r /etc/groupx ]
then echo groupx exists
echo foo
else echo groupx DOES NOT exist
fi
