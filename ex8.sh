false && echo hi &
echo bye
#true && echo hi 2 &
#wait
for k in $*
do
    echo $k
done
