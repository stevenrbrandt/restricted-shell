for i in a b c d
do
  for j in e f g
  do
     if [ $i = b ] && [ $j = f ]
     then
        echo $i $j
     fi
  done
done
